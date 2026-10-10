from __future__ import annotations

import os
import sqlite3
from typing import Iterable

from models import FileEntry, SortSpec

TABLES = """
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY,
  parent_id INTEGER,
  name TEXT, path TEXT,
  is_dir INTEGER,
  size INTEGER,
  allocated INTEGER,
  modified TEXT,
  files INTEGER, folders INTEGER,
  name_lc TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""
# Индекс импорт создаёт после загрузки данных (так быстрее)
INDEX = "CREATE INDEX IF NOT EXISTS ix_parent ON entries(parent_id)"
# Порядок полей: id, parent_id, name, path, is_dir, size, allocated,
# modified, files, folders, name_lc
INSERT_SQL = "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?)"

# Белый список полей сортировки (в SQL нельзя подставлять произвольный текст).
# name_lc — имя в нижнем регистре, считается в Python: работает и для кириллицы
SORT_SQL = {
    "name": "e.name_lc",
    "size": "e.size",
    "modified": "e.modified",
    "files": "e.files",
}

SELECT = """
SELECT e.id, e.parent_id, e.name, e.path, e.is_dir, e.size, e.allocated,
       e.modified, e.files, e.folders,
       p.size AS parent_size,
       EXISTS(SELECT 1 FROM entries c WHERE c.parent_id = e.id) AS has_children
FROM entries e LEFT JOIN entries p ON p.id = e.parent_id
"""


def _to_entry(r) -> FileEntry:
    return FileEntry(r[0], r[1], r[2], r[3], bool(r[4]), r[5], r[6],
                     r[7], r[8], r[9], r[10], bool(r[11]))


def _order_by(sort: SortSpec) -> str:
    expr = SORT_SQL.get(sort.field, "e.size")
    direction = "DESC" if sort.descending else "ASC"
    parts = []
    if sort.dirs_first:
        parts.append("e.is_dir DESC")
    parts.append(f"{expr} {direction}")
    parts.append("e.name_lc")  # стабильный порядок при равенстве
    parts.append("e.id")
    return "ORDER BY " + ", ".join(parts)


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(TABLES + INDEX + ";")
    except sqlite3.Error:  # например, файл не является базой
        conn.close()
        raise
    return conn


class Catalog:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        self.conn = _connect(path)

    # ---------- управление базой ----------
    def open(self, path: str) -> None:
        """Открывает базу из файла. При ошибке старое соединение остаётся."""
        conn = _connect(path)
        self.conn.close()
        self.conn, self.path = conn, path

    def replace_with(self, tmp_path: str, final_path: str) -> None:
        """Подмена базы готовым временным файлом (os.replace атомарен)."""
        self.conn.close()
        try:
            os.replace(tmp_path, final_path)
        except OSError:
            self.conn = _connect(self.path)  # вернуть прежнюю базу
            raise
        self.conn, self.path = _connect(final_path), final_path

    def meta(self, key: str) -> str | None:
        """Служебное значение (размер и mtime исходного CSV)."""
        try:
            row = self.conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        except sqlite3.Error:
            return None
        return row[0] if row else None

    # ---------- данные ----------
    def clear(self) -> None:
        self.conn.execute("DELETE FROM entries")
        self.conn.commit()

    def insert_many(self, rows: Iterable[tuple]) -> None:
        """Строки: (id, parent_id, name, path, is_dir, size, allocated, modified, files, folders)."""
        self.conn.executemany(
            INSERT_SQL, [(*r, r[2].lower()) for r in rows]  # + name_lc
        )
        self.conn.commit()

    def entry(self, entry_id: int) -> FileEntry | None:
        row = self.conn.execute(SELECT + " WHERE e.id = ?", (entry_id,)).fetchone()
        return _to_entry(row) if row else None

    def children(self, parent_id: int | None, sort: SortSpec,
                 limit: int, offset: int = 0) -> list[FileEntry]:
        """Дочерние записи (parent_id=None — корни). Сортирует SQLite."""
        sql = SELECT + " WHERE e.parent_id IS ? " + _order_by(sort) + " LIMIT ? OFFSET ?"
        rows = self.conn.execute(sql, (parent_id, limit, offset)).fetchall()
        return [_to_entry(r) for r in rows]