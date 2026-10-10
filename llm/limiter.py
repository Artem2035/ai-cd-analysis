"""Фиксированные окна по календарным минутам: запросы (RPM) и токены (TPM).

Счётчики обнуляются при смене минуты (12:00, 12:01, ...). Только в памяти.
"""
import time


class Limiter:
    def __init__(self, tpm: int, rpm: int, clock=time.time):
        self.tpm = tpm
        self.rpm = rpm
        self._clock = clock        # настенные часы: границы минут по ним
        self._minute = -1          # номер текущей минуты (время // 60)
        self._requests = 0
        self._tokens = 0

    def _roll(self) -> float:
        """Сбрасывает счётчики, если началась новая минута; возвращает «сейчас»."""
        now = self._clock()
        minute = int(now // 60)
        if minute != self._minute:
            self._minute = minute
            self._requests = 0
            self._tokens = 0
        return now

    def check(self, estimate: int) -> float:
        """Сколько секунд ждать до новой минуты (0 — можно отправлять).

        ValueError, если запрос не влезает в лимит даже на пустой минуте.
        """
        if estimate > self.tpm:
            raise ValueError(
                f"Запрос слишком большой для лимита {self.tpm} токенов в "
                f"минуту (оценка {estimate}). Сократите текст или "
                f"MAX_OUTPUT_TOKENS.")
        now = self._roll()
        if self._requests >= self.rpm or self._tokens + estimate > self.tpm:
            return 60.0 - now % 60
        return 0.0

    def start(self, tokens: int) -> list:
        """Учитывает отправку с оценкой токенов; возвращает метку для finish."""
        self._roll()
        self._requests += 1
        self._tokens += tokens
        return [self._minute, tokens]

    def finish(self, ticket: list, tokens: int) -> None:
        """Заменяет оценку фактическим usage, если минута ещё та же."""
        self._roll()
        if ticket[0] == self._minute:
            self._tokens = max(0, self._tokens + tokens - ticket[1])
        ticket[1] = tokens