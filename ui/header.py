import tkinter as tk
from tkinter import ttk

from ui import theme


class Header(tk.Frame):
    """Верхняя панель: ряд кнопок, ниже статус и прогресс."""

    def __init__(self, parent, controller):
        super().__init__(parent, bg=theme.PANEL, height=96)
        self.pack_propagate(False)

        # Ряд 1: кнопки команд
        buttons = tk.Frame(self, bg=theme.PANEL)
        buttons.pack(fill="x", padx=20, pady=(14, 0))

        self.run = self._button(buttons, "▶  Запуск", "Accent.TButton",
                                controller.start_analysis)
        self.run.pack(side="left")
        self.from_csv = self._button(buttons, "Обновить из CSV", "Plain.TButton",
                                     controller.refresh_csv)
        self.from_csv.pack(side="left", padx=(10, 0))
        self.from_db = self._button(buttons, "Обновить из базы", "Plain.TButton",
                                    controller.refresh_db)
        self.from_db.pack(side="left", padx=(10, 0))
        self.cancel = self._button(buttons, "Отмена импорта", "Plain.TButton",
                                   controller.cancel_import)
        self.cancel.pack(side="left", padx=(10, 0))

        # Ряд 2: статус и прогресс
        info = tk.Frame(self, bg=theme.PANEL)
        info.pack(fill="x", padx=20, pady=(12, 0))

        self.status = tk.Label(info, text="Готов к работе", bg=theme.PANEL,
                               fg=theme.MUTED, font=theme.font(9))
        self.status.pack(side="left")

        self.progress = ttk.Progressbar(
            info, mode="determinate", maximum=100,
            style="Accent.Horizontal.TProgressbar")
        self.progress.pack(side="right", fill="x", expand=True, padx=(16, 0))

        self.set_busy(False)

    @staticmethod
    def _button(parent, text, style, command) -> ttk.Button:
        return ttk.Button(parent, text=text, style=style, cursor="hand2",
                          command=command)

    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def set_progress(self, value: float) -> None:
        self.progress["value"] = value

    def set_busy(self, busy: bool) -> None:
        """Во время импорта доступна только «Отмена импорта»."""
        for b in (self.run, self.from_csv, self.from_db):
            b.state(["disabled"] if busy else ["!disabled"])
        self.cancel.state(["!disabled"] if busy else ["disabled"])