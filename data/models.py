from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FileEntry:
    """Одна запись каталога (файл или папка)."""
    id: int
    parent_id: int | None
    name: str
    path: str
    is_dir: bool
    size: int                  # байты
    allocated: int
    modified: str
    files: int | None          # только у папок
    folders: int | None        # только у папок
    parent_size: int | None    # размер родителя, для «% от родителя»
    has_children: bool


@dataclass
class SortSpec:
    """Порядок сортировки; field — ключ из белого списка в catalog.py."""
    field: str = "size"
    descending: bool = True
    dirs_first: bool = True