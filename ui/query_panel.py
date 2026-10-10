import tkinter as tk
from tkinter import ttk

from ui import theme


def _readonly_text(parent, height=None) -> tk.Text:
    opts = {"height": height} if height else {}
    return tk.Text(parent, wrap="word", font=theme.font(10), bg="#FCFCFE",
                   fg=theme.TEXT, relief="flat", padx=12, pady=12,
                   highlightthickness=1, highlightbackground=theme.BORDER,
                   highlightcolor=theme.ACCENT, state="disabled", **opts)


class QueryPanel(tk.Frame):
    """Правая панель: запрос по «?», поле ответа, кнопка «Выполнить»."""

    def __init__(self, parent, controller):
        super().__init__(parent, bg=theme.PANEL)

        top = tk.Frame(self, bg=theme.PANEL)
        top.pack(fill="x", padx=18, pady=(16, 12))
        tk.Label(top, text="Запрос", bg=theme.PANEL, fg=theme.TEXT,
                 font=theme.font(13, True)).pack(anchor="w")
        self.target = tk.Label(top, bg=theme.PANEL, fg=theme.MUTED,
                               font=theme.font(9), anchor="w", justify="left")
        self.target.pack(anchor="w", fill="x", pady=(5, 0))

        self.query = _readonly_text(self, height=7)
        self.query.pack(fill="x", padx=18)

        tk.Label(self, text="Ответ", bg=theme.PANEL, fg=theme.MUTED,
                 font=theme.font(9, True)).pack(anchor="w", padx=18,
                                                pady=(14, 6))
        box = tk.Frame(self, bg=theme.PANEL)
        box.pack(fill="both", expand=True, padx=18)
        scroll = ttk.Scrollbar(box, orient="vertical")
        self.answer = _readonly_text(box)
        self.answer.configure(yscrollcommand=scroll.set)
        scroll.configure(command=self.answer.yview)
        scroll.pack(side="right", fill="y")
        self.answer.pack(side="left", fill="both", expand=True)

        bottom = tk.Frame(self, bg=theme.PANEL)
        bottom.pack(fill="x", padx=18, pady=16)
        self.run = ttk.Button(bottom, text="Выполнить", style="Accent.TButton",
                              cursor="hand2", command=controller.run_query)
        self.run.pack(side="right")

        self.show_query(None, "", "")

    @staticmethod
    def _set(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def show_query(self, entry_id, path: str, text: str) -> None:
        """Колбэк контроллера on_query_opened (None — элемент не выбран)."""
        self._set(self.answer, "")
        if entry_id is None:
            self.target.configure(text="Нажмите «?» у элемента дерева")
            self._set(self.query, "")
            self.run.state(["disabled"])
        else:
            self.target.configure(text=path)
            self._set(self.query, text)
            self.run.state(["!disabled"])

    def show_answer(self, text: str) -> None:
        """Колбэк контроллера on_answer (будет использован на этапе 3)."""
        self._set(self.answer, text)