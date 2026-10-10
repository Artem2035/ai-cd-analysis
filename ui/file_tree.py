from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from columns import ASK_ID, COLUMNS, NAME_COLUMN
from models import FileEntry

from ui import theme


class FileTree(tk.Frame):
    """Левая панель: ленивое дерево на ttk.Treeview."""

    def __init__(self, parent, controller):
        super().__init__(parent, bg=theme.PANEL)
        self.controller = controller
        # iid строки «Показать ещё…» -> (родитель в дереве, id папки, смещение)
        self._more: dict[str, tuple[str, int | None, int]] = {}
        self._build()

    # ---------- построение ----------
    def _build(self) -> None:
        tk.Label(self, text="Структура файлов", bg=theme.PANEL, fg=theme.TEXT,
                 font=theme.font(13, True), anchor="w"
                 ).pack(fill="x", padx=14, pady=(16, 12))
        # Сюда позже добавится поле поиска

        box = tk.Frame(self, bg=theme.PANEL)
        box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(box, columns=[c.id for c in COLUMNS],
                                 selectmode="browse")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.column("#0", width=NAME_COLUMN.width, minwidth=140,
                         stretch=True, anchor="w")
        for c in COLUMNS:
            self.tree.column(c.id, width=c.width, minwidth=30,
                             stretch=False, anchor=c.anchor)
        self.tree.tag_configure("more", foreground=theme.ACCENT)

        self._update_headings()
        self._apply_visible()

        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<<TreeviewOpen>>", self._on_open)
        self.tree.bind("<<TreeviewClose>>", self._on_close)
        for seq in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
            self.tree.bind(seq, self._on_header_menu, add="+")

    def _update_headings(self) -> None:
        """Заголовки, команды сортировки и стрелка текущей сортировки."""
        sort = self.controller.sort
        arrow = " ▼" if sort.descending else " ▲"
        marked = False
        for col in (NAME_COLUMN, *COLUMNS):
            title = col.title
            if not marked and col.db_field == sort.field:
                title += arrow
                marked = True
            heading_id = "#0" if col is NAME_COLUMN else col.id
            command = (lambda c=col: self._on_heading(c)) if col.db_field else ""
            self.tree.heading(heading_id, text=title, anchor=col.anchor,
                              command=command)

    def _apply_visible(self) -> None:
        self.tree["displaycolumns"] = [c.id for c in COLUMNS if c.visible]

    # ---------- загрузка данных ----------
    def reload(self) -> None:
        """Полная перерисовка: грузятся только корни и раскрытые узлы."""
        self.tree.delete(*self.tree.get_children())
        self._more.clear()
        self._fill("", None)
        sel = self.controller.selected_id
        if sel is not None and self.tree.exists(str(sel)):
            self.tree.selection_set(str(sel))
            self.tree.see(str(sel))

    def _fill(self, tree_parent: str, parent_id: int | None, offset: int = 0) -> None:
        entries, has_more = self.controller.children(parent_id, offset)
        for entry in entries:
            self._insert(tree_parent, entry)
        if has_more:
            next_offset = offset + len(entries)
            iid = f"more:{parent_id}:{next_offset}"
            self._more[iid] = (tree_parent, parent_id, next_offset)
            self.tree.insert(tree_parent, "end", iid=iid, text="Показать ещё…",
                             tags=("more",))

    def _insert(self, tree_parent: str, e: FileEntry) -> None:
        iid = str(e.id)  # iid = id из базы
        self.tree.insert(tree_parent, "end", iid=iid,
                         text=NAME_COLUMN.format(e),
                         values=[c.format(e) for c in COLUMNS])
        if e.is_dir and e.has_children:
            if e.id in self.controller.expanded:
                self._fill(iid, e.id)
                self.tree.item(iid, open=True)
            else:
                # фиктивный потомок, чтобы появился треугольник
                self.tree.insert(iid, "end", iid=f"dummy:{e.id}", text="")

    def _load_more(self, iid: str) -> None:
        tree_parent, parent_id, offset = self._more.pop(iid)
        self.tree.delete(iid)
        self._fill(tree_parent, parent_id, offset)

    # ---------- события ----------
    def _column_id(self, event) -> str:
        """id колонки под курсором с учётом скрытых колонок."""
        index = int(self.tree.identify_column(event.x)[1:])
        if index == 0:
            return "#0"
        display = self.tree["displaycolumns"]
        return display[index - 1] if index - 1 < len(display) else ""

    def _is_ask_cell(self, event, iid: str) -> bool:
        return (iid.isdigit()
                and self.tree.identify_region(event.x, event.y) == "cell"
                and self._column_id(event) == ASK_ID)

    def _on_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid in self._more:
            self._load_more(iid)
            return "break"
        if self._is_ask_cell(event, iid):
            self.controller.ask(int(iid))
            return "break"  # выбор строки не меняется
        return None

    def _on_motion(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        hand = iid in self._more or self._is_ask_cell(event, iid)
        self.tree.configure(cursor="hand2" if hand else "")

    def _on_select(self, _event) -> None:
        sel = self.tree.selection()
        if sel and sel[0].isdigit():
            self.controller.select(int(sel[0]))

    def _on_open(self, _event) -> None:
        iid = self.tree.focus()
        if not iid.isdigit():
            return
        children = self.tree.get_children(iid)
        if children and children[0].startswith("dummy:"):
            self.tree.delete(children[0])
            self._fill(iid, int(iid))
        self.controller.toggle(int(iid), True)

    def _on_close(self, _event) -> None:
        iid = self.tree.focus()
        if iid.isdigit():
            self.controller.toggle(int(iid), False)

    def _on_heading(self, col) -> None:
        self.controller.sort_by(col.db_field)
        self._update_headings()
        self.reload()

    def _on_header_menu(self, event) -> None:
        """Правый клик по заголовку: показать/скрыть колонки."""
        if self.tree.identify_region(event.x, event.y) != "heading":
            return
        menu = tk.Menu(self, tearoff=0)
        for c in COLUMNS:
            if c.id == ASK_ID:
                continue
            mark = "✓" if c.visible else "    "
            menu.add_command(label=f"{mark}  {c.title}",
                             command=lambda c=c: self._toggle_column(c))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _toggle_column(self, col) -> None:
        col.visible = not col.visible
        self._apply_visible()