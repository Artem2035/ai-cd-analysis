"""Фоновый импорт CSV-экспорта WizTree в SQLite. О Tkinter не знает."""
from __future__ import annotations

import csv
import heapq
import os
import queue
import sqlite3
import threading
from typing import Iterator

from catalog import INDEX, INSERT_SQL, TABLES

BATCH = 50_000     # строк в одной вставке
TICK = 20_000      # как часто слать прогресс и проверять отмену
HEADER_SCAN = 5    # сколько первых строк просматривать в поисках заголовка

# Имена колонок в заголовке (русские и английские), в нижнем регистре
ALIASES = {
    "name": ("имя файла", "file name", "name"),
    "size": ("размер", "size"),
    "allocated": ("на диске", "allocated"),
    "modified": ("изменено", "modified"),
    "files": ("файлы", "files"),
    "folders": ("папки", "folders"),
}


class _Cancelled(Exception):
    pass


# ---------- разбор строк ----------
def _decode(raw: bytes) -> str:
    """UTF-8 (с BOM или без), для «чужой» строки — запасной вариант cp1251."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251", errors="replace")


def _split(path: str) -> tuple[str, str | None]:
    """Путь -> (имя, путь родителя с «\\» на конце); у корня родителя нет."""
    head, sep, tail = path.rstrip("\\").rpartition("\\")
    if not sep:
        return path, None
    return tail, head + "\\"


def _find_columns(row: list[str]) -> dict[str, int] | None:
    """Индексы колонок по именам заголовка; нужны хотя бы имя и размер."""
    names = [c.strip().lower() for c in row]
    found = {}
    for key, aliases in ALIASES.items():
        for i, n in enumerate(names):
            if n in aliases:
                found[key] = i
                break
    return found if "name" in found and "size" in found else None


def _cell(row: list[str], i: int | None) -> str:
    # строки в файле «рваные»: недостающие поля считаются пустыми
    return row[i].strip() if i is not None and i < len(row) else ""


def _num(row: list[str], i: int | None, default):
    try:
        return int(_cell(row, i))
    except ValueError:
        return default


def _date(s: str) -> str:
    """2026.09.28 23:27:32 -> 2026-09-28 23:27:32."""
    if len(s) >= 10 and s[4] == "." and s[7] == ".":
        return s[:4] + "-" + s[5:7] + "-" + s[8:]
    return s


def _parse(row: list[str], c: dict[str, int]) -> tuple | None:
    """Строка CSV -> (path, size, allocated, modified, files, folders) или None."""
    path = _cell(row, c["name"])
    size = _num(row, c["size"], -1)
    if not path or size < 0:
        return None
    return (path, size, _num(row, c.get("allocated"), size),
            _date(_cell(row, c.get("modified"))),
            _num(row, c.get("files"), None), _num(row, c.get("folders"), None))


# ---------- сборка строк базы ----------
class _Builder:
    """Привязывает детей к родителям и достраивает недостающие папки.

    Элемент: (id, name, path, is_dir, size, allocated, modified, files, folders).
    Порядок строк в файле не важен: ребёнок, пришедший раньше родителя,
    ждёт в pending. В памяти только словарь «путь папки -> id».
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.ids: dict[str, int] = {}
        self.pending: dict[str, list[tuple]] = {}
        self.buf: list[tuple] = []
        self.next_id = 1

    def new_id(self) -> int:
        self.next_id += 1
        return self.next_id - 1

    def add(self, item: tuple, parent_path: str | None) -> None:
        if parent_path is None:
            self.emit(item, None)
        elif parent_path in self.ids:
            self.emit(item, self.ids[parent_path])
        else:
            self.pending.setdefault(parent_path, []).append(item)

    def register(self, path: str, folder_id: int) -> None:
        """Папка появилась: сразу привязываем ждавших её детей."""
        self.ids[path] = folder_id
        for child in self.pending.pop(path, ()):
            self.emit(child, folder_id)

    def emit(self, item: tuple, parent_id: int | None) -> None:
        self.buf.append((item[0], parent_id, *item[1:], item[1].lower()))
        if len(self.buf) >= BATCH:
            self.flush()

    def flush(self) -> None:
        self.conn.executemany(INSERT_SQL, self.buf)
        self.conn.commit()
        self.buf.clear()

    def finish(self) -> None:
        """Родители, которых нет в файле, становятся виртуальными папками.

        Идём от самых длинных путей к коротким: вложенная виртуальная папка
        всегда обработана раньше своей родительской, и суммы получаются верными.
        """
        heap = [(-len(p), p) for p in self.pending]
        heapq.heapify(heap)
        while heap:
            _, path = heapq.heappop(heap)
            children = self.pending.pop(path, None)
            if children is None:
                continue
            vid = self.new_id()
            self.ids[path] = vid
            size = alloc = files = folders = 0
            for c in children:
                size += c[4]
                alloc += c[5]
                if c[3]:
                    files += c[7] or 0
                    folders += 1 + (c[8] or 0)
                else:
                    files += 1
                self.emit(c, vid)
            name, parent_path = _split(path)
            self.add((vid, name, path, 1, size, alloc, "", files, folders),
                     parent_path)
            if parent_path in self.pending:
                heapq.heappush(heap, (-len(parent_path), parent_path))
        self.flush()


# ---------- импорт ----------
class WizTreeImport:
    """Импорт в потоке. Сообщения для UI лежат в self.messages:
    ("progress", процент, текст) | ("done", загружено, пропущено)
    | ("error", текст) | ("cancelled",)."""

    def __init__(self, csv_path: str, db_path: str):
        self.csv_path = csv_path
        self.db_path = db_path
        self.tmp_path = db_path + ".tmp"
        self.messages: queue.Queue = queue.Queue()
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._pos = 0  # прочитано байт

    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def join(self, timeout: float) -> None:
        if self._thread.is_alive():
            self._thread.join(timeout)

    def _run(self) -> None:
        try:
            loaded, skipped = self._import()
        except _Cancelled:
            self._remove_tmp()
            self.messages.put(("cancelled",))
        except Exception as exc:  # любая ошибка: старая база не тронута
            self._remove_tmp()
            self.messages.put(("error", str(exc)))
        else:
            self.messages.put(("done", loaded, skipped))

    def _remove_tmp(self) -> None:
        try:
            os.remove(self.tmp_path)
        except FileNotFoundError:
            pass

    def _import(self) -> tuple[int, int]:
        self._remove_tmp()  # хвост прошлого неудачного запуска
        stat = os.stat(self.csv_path)
        conn = sqlite3.connect(self.tmp_path)
        try:
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA synchronous=OFF")
            conn.executescript(TABLES)
            loaded, skipped = self._load(conn, stat.st_size)
            self._check_cancel()
            self.messages.put(("progress", 97, "Создание индекса…"))
            conn.execute(INDEX)
            conn.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", [
                ("source_size", str(stat.st_size)),
                ("source_mtime", str(stat.st_mtime_ns)),
            ])
            conn.commit()
        finally:
            conn.close()
        return loaded, skipped

    def _lines(self, f) -> Iterator[str]:
        # бинарное чтение: так известна позиция в файле для прогресса
        for raw in f:
            self._pos += len(raw)
            yield _decode(raw)

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise _Cancelled

    def _load(self, conn: sqlite3.Connection, total: int) -> tuple[int, int]:
        total = max(total, 1)
        builder = _Builder(conn)
        cols = None
        scanned = seen = loaded = skipped = 0
        self._pos = 0
        with open(self.csv_path, "rb") as f:
            reader = csv.reader(self._lines(f))
            while True:
                try:
                    row = next(reader)
                except StopIteration:
                    break
                except csv.Error:  # битая строка
                    skipped += 1
                    continue

                if cols is None:  # ищем заголовок, комментарий пропускаем
                    cols = _find_columns(row)
                    scanned += 1
                    if cols is None and scanned >= HEADER_SCAN:
                        break
                    continue
                if not row:
                    continue

                seen += 1
                if seen % TICK == 0:
                    self._check_cancel()
                    pct = int(self._pos / total * 95)
                    text = f"Импорт CSV: {seen:,} строк".replace(",", " ")
                    self.messages.put(("progress", pct, text))

                parsed = _parse(row, cols)
                if parsed is None:
                    skipped += 1
                    continue
                path, size, alloc, modified, files, folders = parsed
                is_dir = path.endswith("\\")
                if is_dir and path in builder.ids:  # дубликат папки
                    skipped += 1
                    continue
                name, parent_path = _split(path)
                item = (builder.new_id(), name, path, int(is_dir), size, alloc,
                        modified, files if is_dir else None,
                        folders if is_dir else None)
                if is_dir:
                    builder.register(path, item[0])
                builder.add(item, parent_path)
                loaded += 1

        if cols is None:
            raise ValueError("Не найдены колонки «Имя файла» и «Размер»")
        if loaded == 0:
            raise ValueError("В файле нет подходящих строк")
        self._check_cancel()
        self.messages.put(("progress", 96, "Достраиваю папки…"))
        builder.finish()
        return loaded, skipped