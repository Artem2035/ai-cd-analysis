"""Скользящее окно на минуту: запросы (RPM) и токены (TPM). Только в памяти."""
import time
from collections import deque

WINDOW = 60.0


class Limiter:
    def __init__(self, tpm: int, rpm: int, clock=time.monotonic):
        self.tpm = tpm
        self.rpm = rpm
        self._clock = clock
        self._events: deque[list] = deque()  # [время, токены], по возрастанию

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= WINDOW:
            self._events.popleft()

    def check(self, estimate: int) -> float:
        """Сколько секунд ждать до отправки (0 — можно сейчас).

        ValueError, если запрос не влезает в лимит даже на пустом окне.
        """
        if estimate > self.tpm:
            raise ValueError(
                f"Запрос слишком большой для лимита {self.tpm} токенов в "
                f"минуту (оценка {estimate}). Сократите текст или "
                f"MAX_OUTPUT_TOKENS.")
        now = self._clock()
        self._prune(now)
        wait = 0.0
        if len(self._events) >= self.rpm:
            # слот освободится, когда истечёт нужное по счёту событие
            idx = len(self._events) - self.rpm
            wait = self._events[idx][0] + WINDOW - now
        used = sum(e[1] for e in self._events)
        if used + estimate > self.tpm:
            for e in self._events:
                used -= e[1]
                if used + estimate <= self.tpm:
                    wait = max(wait, e[0] + WINDOW - now)
                    break
        return max(wait, 0.0)

    def start(self, tokens: int) -> list:
        """Учитывает отправку с оценкой токенов; возвращает метку для finish."""
        ticket = [self._clock(), tokens]
        self._events.append(ticket)
        return ticket

    @staticmethod
    def finish(ticket: list, tokens: int) -> None:
        """Заменяет оценку фактическим usage из ответа."""
        ticket[1] = tokens