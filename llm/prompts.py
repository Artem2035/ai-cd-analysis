"""Шаблон запроса по «?». Текст примерный: уточняется на этапе реального запроса."""
from data.format import format_size
from data.models import FileEntry

QUERY_TEMPLATE = (
    "Что это за объект ({kind}) и безопасно ли его удалить?\n"
    "Имя: {name}\n"
    "Путь: {path}\n"
    "Размер: {size}\n"
    "Изменён: {modified}"
)


def build_query(e: FileEntry) -> str:
    """Подставляет данные выбранного элемента в шаблон."""
    return QUERY_TEMPLATE.format(
        kind="папка" if e.is_dir else "файл",
        name=e.name, path=e.path,
        size=format_size(e.size), modified=e.modified or "—")