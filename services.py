from typing import Callable

from models import FileEntry


class NetworkService:
    """Заглушка запроса «?». О Tkinter не знает: планировщик передаётся снаружи."""

    def __init__(self, schedule: Callable[[int, Callable[[], None]], object]):
        self._schedule = schedule  # root.after

    def ask(self, entry: FileEntry, on_done: Callable[[str], None]) -> None:
        # Формат запроса/ответа не определён: имитируем задержку сети
        answer = f"Фиктивный ответ для «{entry.name}»"
        self._schedule(1200, lambda: on_done(answer))