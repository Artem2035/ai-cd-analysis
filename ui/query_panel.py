import tkinter as tk
from tkinter import ttk

from ui import theme


def _text(parent, height=None, state="disabled") -> tk.Text:
    opts = {"height": height} if height else {}
    return tk.Text(parent, wrap="word", font=theme.font(10), bg="#FCFCFE",
                   fg=theme.TEXT, relief="flat", padx=12, pady=12,
                   highlightthickness=1, highlightbackground=theme.BORDER,
                   highlightcolor=theme.ACCENT, state=state, **opts)


class QueryPanel(tk.Frame):
    """Правая панель: редактируемый промт, поле ответа, кнопка «Выполнить»."""

    def __init__(self, parent, controller):
        super().__init__(parent, bg=theme.PANEL)
        self._has_query = False  # выбран ли элемент
        self._busy = False       # идёт запрос к модели

        # Нижняя полоса упаковывается первой: кнопка всегда остаётся видимой,
        # при нехватке места сжимается поле ответа
        bottom = tk.Frame(self, bg=theme.PANEL)
        bottom.pack(side="bottom", fill="x", padx=18, pady=16)
        self.run = ttk.Button(bottom, text="Выполнить", style="Accent.TButton",
                              cursor="hand2", command=self._on_run)
        self.run.pack(side="right")
        self.controller = controller

        top = tk.Frame(self, bg=theme.PANEL)
        top.pack(fill="x", padx=18, pady=(16, 12))
        tk.Label(top, text="Запрос", bg=theme.PANEL, fg=theme.TEXT,
                 font=theme.font(13, True)).pack(anchor="w")
        self.target = tk.Label(top, bg=theme.PANEL, fg=theme.MUTED,
                               font=theme.font(9), anchor="w", justify="left")
        self.target.pack(anchor="w", fill="x", pady=(5, 0))

        # Полный промт (инструкции + данные): длинный, поэтому с прокруткой
        qbox = tk.Frame(self, bg=theme.PANEL)
        qbox.pack(fill="x", padx=18)
        qscroll = ttk.Scrollbar(qbox, orient="vertical")
        self.query = _text(qbox, height=8)  # редактируется, когда выбран элемент
        self.query.configure(yscrollcommand=qscroll.set)
        qscroll.configure(command=self.query.yview)
        qscroll.pack(side="right", fill="y")
        self.query.pack(side="left", fill="x", expand=True)

        tk.Label(self, text="Ответ", bg=theme.PANEL, fg=theme.MUTED,
                 font=theme.font(9, True)).pack(anchor="w", padx=18,
                                                pady=(14, 6))
        box = tk.Frame(self, bg=theme.PANEL)
        box.pack(fill="both", expand=True, padx=18)
        scroll = ttk.Scrollbar(box, orient="vertical")
        self.answer = _text(box)
        self.answer.configure(yscrollcommand=scroll.set)
        scroll.configure(command=self.answer.yview)
        scroll.pack(side="right", fill="y")
        self.answer.pack(side="left", fill="both", expand=True)

        self.show_query(None, "", "")

    def _on_run(self) -> None:
        self.controller.run_query(self.query.get("1.0", "end-1c"))

    def _refresh_run(self) -> None:
        """Кнопка активна, только если выбран элемент и нет запроса в работе."""
        ok = self._has_query and not self._busy
        self.run.state(["!disabled"] if ok else ["disabled"])

    @staticmethod
    def _set(widget: tk.Text, text: str) -> None:
        """Заменяет текст, сохраняя состояние (normal/disabled) поля."""
        state = str(widget.cget("state"))
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state=state)

    def show_query(self, entry_id, path: str, text: str) -> None:
        """Колбэк контроллера on_query_opened (None — элемент не выбран)."""
        self._set(self.answer, "")
        self._has_query = entry_id is not None
        if entry_id is None:
            self.target.configure(text="Нажмите «?» у элемента дерева")
            self.query.configure(state="disabled")
            self._set(self.query, "")
        else:
            self.target.configure(text=path)
            self.query.configure(state="normal")
            self._set(self.query, text)
        self._refresh_run()

    def set_busy(self, busy: bool) -> None:
        """Колбэк контроллера on_query_busy: блокировка на время запроса."""
        self._busy = busy
        self._refresh_run()

    def show_answer(self, text: str) -> None:
        """Колбэк контроллера on_answer."""
        self._set(self.answer, text)