"""Настройки из .env рядом с main.py. Нет файла или ключа: значение по умолчанию."""
from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _read_env(path: str) -> dict[str, str]:
    """Мини-разбор .env: строки KEY=VALUE, # — комментарий, кавычки снимаются."""
    values: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


_env = _read_env(os.path.join(BASE_DIR, ".env"))


def _get(key: str, default: str) -> str:
    # переменная окружения ОС важнее файла
    return os.environ.get(key, _env.get(key, default))


def _get_int(key: str, default: int) -> int:
    try:
        value = int(_get(key, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


CSV_NAME = _get("CSV_NAME", "wiztree_result.csv")
DB_NAME = _get("DB_NAME", "wiztree_result.db")
PAGE_SIZE = _get_int("PAGE_SIZE", 1000)
POLL_MS = _get_int("POLL_MS", 100)