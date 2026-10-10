"""Запрос к Groq API (chat completions) в потоке. О Tkinter не знает."""
from __future__ import annotations

import json
import queue
import socket
import threading
import urllib.error
import urllib.request
from typing import Callable

import config
from llm.prompts import RESPONSE_SCHEMA

_TIMEOUTS = (TimeoutError, socket.timeout)


class LlmError(Exception):
    """Ошибка запроса с готовым русским текстом.

    kind: "error" | "rate" (429) | "format" (сервер не принял response_format).
    """

    def __init__(self, message: str, kind: str = "error", detail: str = ""):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.detail = detail


def _response_format(strict: bool) -> dict:
    if strict:
        return {"type": "json_schema",
                "json_schema": {"name": "file_advice", "strict": True,
                                "schema": RESPONSE_SCHEMA}}
    return {"type": "json_object"}


def _http_error(exc: urllib.error.HTTPError) -> LlmError:
    detail = ""
    try:
        detail = json.loads(exc.read().decode("utf-8"))["error"]["message"]
    except Exception:  # тело не JSON или пустое
        pass
    code = exc.code
    if code == 401:
        return LlmError("Неверный ключ API (401): проверьте GROQ_API_KEY",
                        detail=detail)
    if code == 403:
        return LlmError("Доступ запрещён (403)", detail=detail)
    if code == 429:
        retry = exc.headers.get("Retry-After") if exc.headers else None
        try:
            text = f"Лимит Groq превышен (429), повторите через {float(retry):.0f} с"
        except (TypeError, ValueError):
            text = "Лимит Groq превышен (429), попробуйте позже"
        return LlmError(text, kind="rate", detail=detail)
    if code == 400 and any(k in detail.lower()
                           for k in ("response_format", "json_schema", "strict")):
        return LlmError("Сервер не принял схему ответа", kind="format",
                        detail=detail)
    if code >= 500:
        return LlmError(f"Сервер Groq недоступен ({code}), попробуйте позже",
                        detail=detail)
    return LlmError(f"Ошибка запроса ({code})", detail=detail)


class NetworkService:
    """Один запрос за раз. Результат через queue.Queue, опрос через schedule."""

    def __init__(self, schedule: Callable[[int, Callable[[], None]], object]):
        self._schedule = schedule  # root.after
        self._strict = True        # после отказа 400 переходим на json_object

    def ask(self, system: str, user: str,
            on_done: Callable[[str, int, int, str], None],
            on_error: Callable[[LlmError], None]) -> None:
        """on_done(текст, токены входа, токены выхода, finish_reason);
        оба колбэка вызываются в потоке UI."""
        box: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, args=(system, user, box),
                         daemon=True).start()  # daemon: окно закрывается сразу
        self._schedule(config.POLL_MS,
                       lambda: self._poll(box, on_done, on_error))

    # ---------- UI-поток ----------
    def _poll(self, box, on_done, on_error) -> None:
        try:
            item = box.get_nowait()
        except queue.Empty:
            self._schedule(config.POLL_MS,
                           lambda: self._poll(box, on_done, on_error))
            return
        if item[0] == "ok":
            on_done(*item[1:])
        else:
            on_error(item[1])

    # ---------- рабочий поток ----------
    def _run(self, system: str, user: str, box: queue.Queue) -> None:
        try:
            box.put(("ok", *self._request(system, user)))
        except LlmError as exc:
            box.put(("error", exc))
        except Exception as exc:  # чтобы UI не остался в ожидании
            box.put(("error", LlmError(f"Непредвиденная ошибка: {exc}")))

    def _request(self, system: str, user: str) -> tuple[str, int, int, str]:
        try:
            data = self._post(system, user, self._strict)
        except LlmError as exc:
            if exc.kind != "format" or not self._strict:
                raise
            self._strict = False  # запоминаем до перезапуска
            data = self._post(system, user, False)
        try:
            choice = data["choices"][0]
            content = choice["message"].get("content") or ""
            finish = choice.get("finish_reason") or ""
            usage = data.get("usage") or {}
            return (content, int(usage.get("prompt_tokens", 0)),
                    int(usage.get("completion_tokens", 0)), finish)
        except (KeyError, IndexError, TypeError, ValueError):
            raise LlmError("Неожиданный формат ответа сервера") from None

    def _post(self, system: str, user: str, strict: bool) -> dict:
        body = {
            "model": config.GROQ_MODEL,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_completion_tokens": config.MAX_OUTPUT_TOKENS,
            "response_format": _response_format(strict),
        }
        if config.REASONING_EFFORT:
            body["reasoning_effort"] = config.REASONING_EFFORT
        req = urllib.request.Request(
            config.GROQ_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {config.GROQ_API_KEY}",
                     "Content-Type": "application/json",
                     "User-Agent": "file-analyzer/1.0"},  # без него Cloudflare может дать 403
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _http_error(exc) from None
        except _TIMEOUTS:
            raise LlmError(f"Таймаут: сервер не ответил за "
                           f"{config.REQUEST_TIMEOUT} с") from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, _TIMEOUTS):
                raise LlmError(f"Таймаут: сервер не ответил за "
                               f"{config.REQUEST_TIMEOUT} с") from None
            raise LlmError("Нет связи с сервером Groq: проверьте сеть",
                           detail=str(exc.reason)) from None
        except json.JSONDecodeError:
            raise LlmError("Сервер вернул не JSON") from None