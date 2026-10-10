import tkinter as tk
from tkinter import ttk

from ui import theme


class Header(tk.Frame):
    """Верхняя панель: кнопка «Анализ», статус, прогресс."""

    def __init__(self, parent, controller):
        super().__init__(parent, bg=theme.PANEL, height=68)
        self.pack_propagate(False)

        ttk.Button(self, text="▶  Анализ", style="Accent.TButton",
                   cursor="hand2", command=controller.start_analysis
                   ).pack(side="left", padx=20, pady=14)

        self.status = tk.Label(self, text="Готов к анализу", bg=theme.PANEL,
                               fg=theme.MUTED, font=theme.font(9))
        self.status.pack(side="left", padx=12)

        self.progress = ttk.Progressbar(
            self, mode="determinate", maximum=100,
            style="Accent.Horizontal.TProgressbar")
        self.progress.pack(side="right", fill="x", expand=True, padx=20)

    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def set_progress(self, value: float) -> None:
        self.progress["value"] = value