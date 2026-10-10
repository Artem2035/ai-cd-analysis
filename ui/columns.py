from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from data.format import format_size, shorten_middle
from data.models import FileEntry

ASK_ID = "ask"  # колонка «?» (её нельзя скрыть)


@dataclass
class Column:
    id: str
    title: str
    db_field: str | None          # поле для сортировки; None — не сортируется
    width: int
    anchor: str = "w"
    format: Callable[[FileEntry], str] = lambda e: ""   # получает запись целиком
    visible: bool = True


def _path(e: FileEntry) -> str:
    # путь без имени файла
    return shorten_middle(e.path.rstrip("\\").rpartition("\\")[0])


def _percent(e: FileEntry) -> str:
    if not e.parent_size:
        return "—"
    return f"{e.size / e.parent_size * 100:.1f} %"


def _files(e: FileEntry) -> str:
    return "" if e.files is None else f"{e.files:,}".replace(",", " ")


# Колонка #0 (с треугольником раскрытия)
NAME_COLUMN = Column(
    "name", "Название", "name", 260,
    format=lambda e: ("📁 " if e.is_dir else "📄 ") + e.name,
)

# Остальные колонки: чтобы добавить поле, достаточно одной строки здесь
COLUMNS = [
    Column("path", "Путь", None, 200, format=_path, visible=False),
    Column("size", "Размер", "size", 80, anchor="e", format=lambda e: format_size(e.size)),
    Column("percent", "% от родителя", "size", 105, anchor="e", format=_percent),
    Column("modified", "Изменён", "modified", 130, format=lambda e: e.modified, visible=False),
    Column("files", "Файлов", "files", 80, anchor="e", format=_files, visible=False),
    Column(ASK_ID, "?", None, 40, anchor="center", format=lambda e: "?"),
]