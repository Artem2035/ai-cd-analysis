from __future__ import annotations

import os
import queue
import sqlite3
from typing import Callable

import config
from catalog import Catalog
from demo_data import load_demo
from models import FileEntry, SortSpec
from query_template import build_query
from services import NetworkService
from wiztree_import import WizTreeImport


def _noop(*args) -> None:
    pass


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


class Controller:
    def __init__(self, catalog: Catalog, network: NetworkService,
                 schedule: Callable[[int, Callable[[], None]], object],
                 base_dir: str):
        self.catalog = catalog
        self.network = network      # пока не используется: подключится на этапе 3
        self._schedule = schedule   # root.after
        self.base_dir = base_dir

        self.sort = SortSpec()
        self.selected_id: int | None = None
        self.expanded: set[int] = set()
        self.query_id: int | None = None   # элемент, открытый в панели запроса
        self._import: WizTreeImport | None = None

        # Колбэки, которые подключает UI
        self.on_status: Callable[[str], None] = _noop
        self.on_progress: Callable[[int], None] = _noop
        self.on_data_reset: Callable[[], None] = _noop
        self.on_query_opened: Callable[[int | None, str, str], None] = _noop
        self.on_answer: Callable[[str], None] = _noop

    # ---------- запуск ----------
    def startup(self) -> None:
        """Открыть базу или загрузить CSV (вызывается после attach)."""
        csv_path = os.path.join(self.base_dir, config.CSV_NAME)
        db_path = csv_path + ".db"

        has_db = os.path.isfile(db_path)
        if has_db:
            try:
                self.catalog.open(db_path)
            except sqlite3.Error:
                has_db = False  # повреждённая база будет заменена импортом

        if os.path.isfile(csv_path) and not (has_db and self._is_actual(csv_path)):
            if has_db:
                self.on_data_reset()  # старые данные видны, пока идёт импорт
            self._start_import(csv_path, db_path)
            return

        self.on_data_reset()
        if has_db:
            self.on_progress(100)
            self.on_status("База открыта")
        else:
            self.on_status(f"Файл экспорта не найден: {config.CSV_NAME}")

    def start_demo(self) -> None:
        """Режим python main.py --demo."""
        self.load_demo()
        self.on_data_reset()
        self.on_progress(100)
        self.on_status("Демонстрационный режим")

    def shutdown(self) -> None:
        """Закрытие окна: отменить импорт, дождаться удаления .tmp."""
        if self._import:
            self._import.cancel()
            self._import.join(2.0)

    def _is_actual(self, csv_path: str) -> bool:
        """База соответствует CSV, если совпали размер и время изменения."""
        st = os.stat(csv_path)
        return (self.catalog.meta("source_size") == str(st.st_size)
                and self.catalog.meta("source_mtime") == str(st.st_mtime_ns))

    # ---------- импорт ----------
    def _start_import(self, csv_path: str, db_path: str) -> None:
        self._import = WizTreeImport(csv_path, db_path)
        self._import.start()
        self.on_progress(0)
        self.on_status("Импорт CSV…")
        self._schedule(config.POLL_MS, self._poll)

    def _poll(self) -> None:
        """Читает очередь потока; Tkinter из потока не вызывается."""
        job = self._import
        if job is None:
            return
        final = None
        try:
            while True:
                msg = job.messages.get_nowait()
                if msg[0] == "progress":
                    self.on_progress(msg[1])
                    self.on_status(msg[2])
                else:
                    final = msg
                    break
        except queue.Empty:
            pass
        if final is None:
            self._schedule(config.POLL_MS, self._poll)
            return
        self._import = None
        self._finish_import(job, final)

    def _finish_import(self, job: WizTreeImport, msg: tuple) -> None:
        kind = msg[0]
        if kind == "done":
            try:
                self.catalog.replace_with(job.tmp_path, job.db_path)
            except OSError as exc:
                self.on_progress(0)
                self.on_status(f"Не удалось заменить базу: {exc}")
                return
            self._reset_state()  # id изменились: выбор и запрос больше не верны
            self.on_data_reset()
            self.on_progress(100)
            self.on_status(f"Загружено {_fmt(msg[1])}, пропущено {_fmt(msg[2])}")
        elif kind == "error":
            self.on_progress(0)
            self.on_status(f"Ошибка импорта: {msg[1]}")
        else:  # cancelled
            self.on_progress(0)
            self.on_status("Импорт отменён")

    def _reset_state(self) -> None:
        self.selected_id = None
        self.expanded.clear()
        self.query_id = None
        self.on_query_opened(None, "", "")

    # ---------- данные ----------
    def load_demo(self) -> None:
        self.catalog.clear()
        load_demo(self.catalog)

    def children(self, parent_id: int | None, offset: int = 0
                 ) -> tuple[list[FileEntry], bool]:
        """Страница дочерних записей и признак «есть ещё»."""
        rows = self.catalog.children(parent_id, self.sort,
                                     config.PAGE_SIZE + 1, offset)
        return rows[:config.PAGE_SIZE], len(rows) > config.PAGE_SIZE

    def toggle(self, entry_id: int, opened: bool) -> None:
        if opened:
            self.expanded.add(entry_id)
        else:
            self.expanded.discard(entry_id)

    def sort_by(self, field: str) -> None:
        """Повторный клик по тому же полю меняет направление."""
        if self.sort.field == field:
            self.sort.descending = not self.sort.descending
        else:
            self.sort.field = field
            self.sort.descending = field != "name"  # имена — по возрастанию

    def select(self, entry_id: int | None) -> None:
        """Выбор строки дерева (нужен, чтобы выбор переживал перерисовку)."""
        self.selected_id = entry_id

    # ---------- «?» и анализ ----------
    def ask(self, entry_id: int) -> None:
        """«?» в строке: открыть панель запроса для элемента (запрос не выполняется)."""
        entry = self.catalog.entry(entry_id)
        if entry is None:
            return
        self.query_id = entry.id
        self.on_query_opened(entry.id, entry.path, build_query(entry))
        self.on_status(f"Запрос подготовлен: {entry.name}")

    def run_query(self) -> None:
        """Кнопка «Выполнить». Заглушка: логика запроса будет на этапе 3."""
        if self.query_id is None:
            self.on_status("Сначала нажмите «?» у элемента дерева")
            return
        self.on_status("Выполнение запроса: пока не реализовано")

    def start_analysis(self) -> None:
        # Заглушка: позже здесь запустится WizTree и создаст CSV
        self.on_status("Пока не реализовано")