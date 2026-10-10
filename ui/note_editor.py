import tkinter as tk
from tkinter import ttk

from ui import theme


class NoteEditor(tk.Frame):
    """Правая панель: заметка выбранного элемента."""

    def __init__(self, parent, controller):
        super().__init__(parent, bg=theme.PANEL)
        self.controller = controller

        top = tk.Frame(self, bg=theme.PANEL)
        top.pack(fill="x", padx=18, pady=(16, 12))
        tk.Label(top, text="Ответ / заметки", bg=theme.PANEL, fg=theme.TEXT,
                 font=theme.font(13, True)).pack(anchor="w")
        self.selected_label = tk.Label(top, text="Элемент не выбран",
                                       bg=theme.PANEL, fg=theme.MUTED,
                                       font=theme.font(9))
        self.selected_label.pack(anchor="w", pady=(5, 0))

        box = tk.Frame(self, bg=theme.PANEL)
        box.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        scroll = ttk.Scrollbar(box, orient="vertical")
        self.text = tk.Text(
            box, wrap="word", undo=True, font=theme.font(10),
            bg="#FCFCFE", fg=theme.TEXT, relief="flat", padx=12, pady=12,
            insertbackground=theme.TEXT, highlightthickness=1,
            highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
            state="disabled", yscrollcommand=scroll.set)
        scroll.configure(command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.bind("<<Modified>>", self._on_modified)

        bottom = tk.Frame(self, bg=theme.PANEL)
        bottom.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Button(bottom, text="Сохранить ответ", style="Accent.TButton",
                   cursor="hand2", command=self._save).pack(side="right")

    def show_note(self, entry_id, path: str, text: str) -> None:
        """Колбэк контроллера on_note_loaded."""
        if entry_id is None:
            self.selected_label.configure(text="Элемент не выбран")
            self._set_text("", enabled=False)
        else:
            self.selected_label.configure(text=path)
            self._set_text(text, enabled=True)

    def _set_text(self, text: str, enabled: bool) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.edit_reset()           # undo не должен откатывать к чужой заметке
        self.text.edit_modified(False)
        if not enabled:
            self.text.configure(state="disabled")

    def _on_modified(self, _event) -> None:
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self.controller.note_edited(self.text.get("1.0", "end-1c"))

    def _save(self) -> None:
        self.controller.save_note(self.text.get("1.0", "end-1c"))