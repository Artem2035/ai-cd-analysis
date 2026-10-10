"""Форматирование для отображения; нужно и ui, и llm."""
from __future__ import annotations


def format_size(n: int) -> str:
    """Байты → «12 КБ», «2.4 МБ». Вызывается только при отображении."""
    if n < 1024:
        return f"{n} Б"
    value = float(n)
    for unit in ("КБ", "МБ", "ГБ", "ТБ"):
        value /= 1024
        if value < 1024 or unit == "ТБ":
            return f"{value:.1f} {unit}" if value < 10 else f"{value:.0f} {unit}"
    return str(n)


def shorten_middle(text: str, limit: int = 40) -> str:
    """Длинный текст обрезается посередине: «D:\\pro…\\modules»."""
    if len(text) <= limit:
        return text
    half = (limit - 1) // 2
    return text[:half] + "…" + text[-(limit - 1 - half):]