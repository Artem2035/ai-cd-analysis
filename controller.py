from __future__ import annotations

from typing import Callable

from catalog import Catalog
from demo_data import load_demo
from models import FileEntry, SortSpec
from services import NetworkService

PAGE_SIZE = 1000  # строк за раз, дальше «Показать ещё…»


def _noop(*args) -> None:
    pass


class Controller:
    def __init__(self, catalog: Catalog, network: NetworkService):
        self.catalog = catalog
        self.network = network

        self.sort = SortSpec()
        self.selected_id: int | None = None
        self.expanded: set[int] = set()
        self.notes: dict[int, str] = {}     # позже заменится классом с load/save
        self.answers: dict[int, str] = {}   # ответы «?» (куда их показывать — пока не решено)
        self.dirty = False                  # есть несохранённые изменения заметки
        self._draft = ""
        self._pending: set[int] = set()

        # Колбэки, которые подключает UI
        self.on_status: Callable[[str], None] = _noop
        self.on_progress: Callable[[int], None] = _noop
        self.on_note_loaded: Callable[[int | None, str, str], None] = _noop
        self.on_data_reset: Callable[[], None] = _noop

    # ---------- данные ----------
    def load_demo(self) -> None:
        self.catalog.clear()
        load_demo(self.catalog)

    def children(self, parent_id: int | None, offset: int = 0
                 ) -> tuple[list[FileEntry], bool]:
        """Страница дочерних записей и признак «есть ещё»."""
        rows = self.catalog.children(parent_id, self.sort, PAGE_SIZE + 1, offset)
        return rows[:PAGE_SIZE], len(rows) > PAGE_SIZE

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

    # ---------- заметки ----------
    def select(self, entry_id: int | None) -> None:
        if entry_id == self.selected_id:
            return
        self._autosave()
        entry = self.catalog.entry(entry_id) if entry_id is not None else None
        self.selected_id = entry.id if entry else None
        self.dirty = False
        if entry:
            self._draft = self.notes.get(entry.id, "")
            self.on_note_loaded(entry.id, entry.path, self._draft)
        else:
            self._draft = ""
            self.on_note_loaded(None, "", "")

    def note_edited(self, text: str) -> None:
        """Редактор сообщает о каждом изменении текста."""
        if self.selected_id is None:
            return
        self._draft = text
        self.dirty = text != self.notes.get(self.selected_id, "")

    def save_note(self, text: str) -> None:
        if self.selected_id is None:
            self.on_status("Сначала выберите элемент дерева")
            return
        self._store(text)
        self.on_status("Ответ сохранён")

    def _autosave(self) -> None:
        """При смене элемента несохранённый текст сохраняется, а не теряется."""
        if self.selected_id is not None and self.dirty:
            self._store(self._draft)
            self.on_status("Заметка сохранена автоматически")

    def _store(self, text: str) -> None:
        if text:
            self.notes[self.selected_id] = text
        else:
            self.notes.pop(self.selected_id, None)
        self._draft = text
        self.dirty = False

    # ---------- «?» и анализ ----------
    def ask(self, entry_id: int) -> None:
        entry = self.catalog.entry(entry_id)
        if entry is None or entry_id in self._pending:
            return
        self._pending.add(entry_id)
        self.on_status(f"Запрос: {entry.name}…")

        def done(answer: str) -> None:
            self._pending.discard(entry_id)
            self.answers[entry_id] = answer
            self.on_status(f"Ответ получен: {entry.name}")

        self.network.ask(entry, done)

    def start_analysis(self) -> None:
        # Этап 1: демо-режим. На этапе 2 здесь будет импорт CSV
        self.select(None)
        self.expanded.clear()
        self.load_demo()
        self.on_data_reset()
        self.on_progress(100)
        self.on_status("Демонстрационный режим")