from __future__ import annotations

import sqlite3
from typing import Iterable

from models import FileEntry, SortSpec

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY,
  parent_id INTEGER,
  name TEXT, path TEXT,
  is_dir INTEGER,
  size INTEGER,
  allocated INTEGER,
  modified TEXT,
  files INTEGER, folders INTEGER
);
CREATE INDEX IF NOT EXISTS ix_parent ON entries(parent_id);
"""

# Белый список полей сортировки (в SQL нельзя подставлять произвольный текст)
SORT_SQL = {
    "name": "e.name COLLATE NOCASE",
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
    parts.append("e.name COLLATE NOCASE")  # стабильный порядок при равенстве
    parts.append("e.id")
    return "ORDER BY " + ", ".join(parts)


class Catalog:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def clear(self) -> None:
        self.conn.execute("DELETE FROM entries")
        self.conn.commit()

    def insert_many(self, rows: Iterable[tuple]) -> None:
        """Строки: (id, parent_id, name, path, is_dir, size, allocated, modified, files, folders)."""
        self.conn.executemany(
            "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?)", rows
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