from __future__ import annotations

import math
import os
import queue
import sqlite3
from typing import Callable

import config
from data.catalog import Catalog
from data.demo_data import load_demo
from data.models import FileEntry, SortSpec
from data.wiztree_import import WizTreeImport
from llm.client import LlmError, NetworkService
from llm.limiter import Limiter
from llm.prompts import (SCHEMA_TEXT, SYSTEM_PROMPT, build_query,
                         format_answer)

CHARS_PER_TOKEN = 2.5  # грубая оценка для русского текста (с запасом)


def _noop(*args) -> None:
    pass


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


class Controller:
    def __init__(self, catalog: Catalog, network: NetworkService,
                 schedule: Callable[[int, Callable[[], None]], object],
                 base_dir: str):
        self.catalog = catalog
        self.network = network
        self._schedule = schedule   # root.after
        self.base_dir = base_dir
        self.csv_path = os.path.join(base_dir, config.CSV_NAME)
        self.db_path = os.path.join(base_dir, config.DB_NAME)
        self.limiter = Limiter(config.LIMIT_TPM, config.LIMIT_RPM)

        self.sort = SortSpec()
        self.selected_id: int | None = None
        self.expanded: set[int] = set()
        self.query_id: int | None = None   # элемент, открытый в панели запроса
        self._import: WizTreeImport | None = None
        self._asking = False               # идёт запрос к модели

        # Колбэки, которые подключает UI
        self.on_status: Callable[[str], None] = _noop
        self.on_progress: Callable[[int], None] = _noop
        self.on_busy: Callable[[bool], None] = _noop
        self.on_result: Callable[[str, bool], None] = _noop
        self.on_data_reset: Callable[[], None] = _noop
        self.on_query_opened: Callable[[int | None, str, str], None] = _noop
        self.on_query_busy: Callable[[bool], None] = _noop
        self.on_answer: Callable[[str], None] = _noop

    # ---------- запуск ----------
    def startup(self) -> None:
        """При запуске только открывает готовую базу; импорт не стартует."""
        if os.path.isfile(self.db_path):
            self.refresh_db()
            return
        if os.path.isfile(self.csv_path):
            self.on_status("Нажмите «Обновить из CSV»")
        else:
            self.on_status(f"Файл экспорта не найден: {config.CSV_NAME}")
        self.on_result("Данные не загружены", False)

    def start_demo(self) -> None:
        """Режим python main.py --demo."""
        self.load_demo()
        self.on_data_reset()
        self.on_progress(100)
        self.on_status("Демонстрационный режим")
        self.on_result("Демонстрационный режим: данные в памяти", False)

    def shutdown(self) -> None:
        """Закрытие окна: отменить импорт, дождаться удаления .tmp.
        Запрос к модели в daemon-потоке: он не мешает закрытию."""
        if self._import:
            self._import.cancel()
            self._import.join(2.0)

    def _is_actual(self, csv_path: str) -> bool:
        """База соответствует CSV, если совпали размер и время изменения."""
        st = os.stat(csv_path)
        return (self.catalog.meta("source_size") == str(st.st_size)
                and self.catalog.meta("source_mtime") == str(st.st_mtime_ns))

    def _error(self, text: str) -> None:
        """Ошибка: подробности в поле итога (красным), в статусе кратко."""
        self.on_status("Ошибка")
        self.on_result(text, True)

    # ---------- команды шапки ----------
    def refresh_db(self) -> None:
        """«Обновить из базы»: переоткрыть .db без импорта."""
        if self._import:
            return
        if not os.path.isfile(self.db_path):
            self._error(f"База не найдена: {config.DB_NAME}")
            return
        try:
            self.catalog.open(self.db_path)
        except sqlite3.Error as exc:
            self._error(f"Не удалось открыть базу: {exc}")
            return
        self._reset_state()  # id могли измениться: выбор и запрос неверны
        self.on_data_reset()
        self.on_progress(100)
        note = ""
        if os.path.isfile(self.csv_path) and not self._is_actual(self.csv_path):
            note = " (CSV изменился, база может быть устаревшей)"
        self.on_status("База открыта")
        self.on_result(f"База открыта: {config.DB_NAME}{note}", False)

    def refresh_csv(self) -> None:
        """«Обновить из CSV»: прочитать файл и записать в базу."""
        if self._import:
            return
        if not os.path.isfile(self.csv_path):
            self._error(f"Файл не найден: {config.CSV_NAME}")
            return
        self._start_import(self.csv_path, self.db_path)

    def cancel_import(self) -> None:
        """«Отмена импорта»: итог придёт из очереди как «cancelled»."""
        if self._import:
            self._import.cancel()
            self.on_status("Отмена импорта…")

    def start_analysis(self) -> None:
        # Заглушка: позже здесь запустится WizTree и создаст CSV
        if self._import:
            return
        self.on_status("Пока не реализовано")

    # ---------- импорт ----------
    def _start_import(self, csv_path: str, db_path: str) -> None:
        self._import = WizTreeImport(csv_path, db_path)
        self._import.start()
        self.on_busy(True)
        self.on_progress(0)
        self.on_status("Импорт CSV…")
        self._schedule(config.POLL_MS, self._poll)

    def _poll(self) -> None:
        """Читает очередь потока; Tkinter из потока не вызывается."""
        job = self._import
        if job is None:
            return
        final = None
        try:
            while True:
                msg = job.messages.get_nowait()
                if msg[0] == "progress":
                    self.on_progress(msg[1])
                    self.on_status(msg[2])
                else:
                    final = msg
                    break
        except queue.Empty:
            pass
        if final is None:
            self._schedule(config.POLL_MS, self._poll)
            return
        self._import = None
        self._finish_import(job, final)

    def _finish_import(self, job: WizTreeImport, msg: tuple) -> None:
        self.on_busy(False)  # единая точка: успех, ошибка и отмена
        kind = msg[0]
        if kind == "done":
            try:
                self.catalog.replace_with(job.tmp_path, job.db_path)
            except OSError as exc:
                self.on_progress(0)
                self._error(f"Не удалось заменить базу: {exc}")
                return
            self._reset_state()  # id изменились: выбор и запрос больше не верны
            self.on_data_reset()
            self.on_progress(100)
            self.on_status("Импорт завершён")
            self.on_result(
                f"Загружено {_fmt(msg[1])}, пропущено {_fmt(msg[2])}", False)
        elif kind == "error":
            self.on_progress(0)
            self._error(f"Ошибка импорта: {msg[1]}")
        else:  # cancelled
            self.on_progress(0)
            self.on_status("Импорт отменён")
            self.on_result("Импорт отменён, прежние данные не изменены", False)

    def _reset_state(self) -> None:
        self.selected_id = None
        self.expanded.clear()
        self.query_id = None
        self.on_query_opened(None, "", "")

    # ---------- данные ----------
    def load_demo(self) -> None:
        self.catalog.clear()
        load_demo(self.catalog)

    def children(self, parent_id: int | None, offset: int = 0
                 ) -> tuple[list[FileEntry], bool]:
        """Страница дочерних записей и признак «есть ещё»."""
        rows = self.catalog.children(parent_id, self.sort,
                                     config.PAGE_SIZE + 1, offset)
        return rows[:config.PAGE_SIZE], len(rows) > config.PAGE_SIZE

    def toggle(self, entry_id: int, opened: bool) -> None:
        if opened:
            self.expanded.add(entry_id)
        else:
            self.expanded.discard(entry_id)

    def sort_by(self, field: str) -> None:
        """Повторный клик по тому же полю меняет направление."""
        if self.sort.field == field:
            self.sort.descending = not self.sort.descending
        else:
            self.sort.field = field
            self.sort.descending = field != "name"  # имена — по возрастанию

    def select(self, entry_id: int | None) -> None:
        """Выбор строки дерева (нужен, чтобы выбор переживал перерисовку)."""
        self.selected_id = entry_id

    # ---------- «?» и запрос ----------
    def ask(self, entry_id: int) -> None:
        """«?» в строке: открыть панель запроса для элемента (запрос не выполняется)."""
        if self._asking:  # ответ должен относиться к тому элементу, для которого отправлен
            self.on_status("Дождитесь ответа на текущий запрос")
            return
        entry = self.catalog.entry(entry_id)
        if entry is None:
            return
        self.query_id = entry.id
        self.on_query_opened(entry.id, entry.path, build_query(entry))
        self.on_status(f"Запрос подготовлен: {entry.name}")

    def _query_error(self, text: str, detail: str = "") -> None:
        """Ошибка запроса: кратко в статус, полностью в поле ответа."""
        self.on_status(text)
        self.on_answer(text + (f"\n\n{detail}" if detail else ""))

    def run_query(self, text: str) -> None:
        """Кнопка «Выполнить»: text уже содержит правки пользователя."""
        if self._asking:
            return
        if self.query_id is None:
            self.on_status("Сначала нажмите «?» у элемента дерева")
            return
        text = text.strip()
        if not text:
            self.on_status("Запрос пуст")
            return
        if not config.GROQ_API_KEY:
            self._query_error("Не задан GROQ_API_KEY: добавьте ключ в файл .env")
            return

        chars = len(SYSTEM_PROMPT) + len(SCHEMA_TEXT) + len(text)
        estimate = int(chars / CHARS_PER_TOKEN) + config.MAX_OUTPUT_TOKENS
        try:
            wait = self.limiter.check(estimate)
        except ValueError as exc:
            self._query_error(str(exc))
            return
        if wait > 0:
            self._query_error(
                f"Лимит запросов: повторите через {math.ceil(wait)} с")
            return

        target = self.query_id
        ticket = self.limiter.start(estimate)
        self._asking = True
        self.on_query_busy(True)
        self.on_answer("Ожидание ответа…")
        self.on_status("Запрос отправлен…")
        self.network.ask(
            SYSTEM_PROMPT, text,
            on_done=lambda *r: self._on_reply(target, ticket, *r),
            on_error=lambda err: self._on_failure(target, ticket, err))

    def _on_reply(self, target: int, ticket: list, content: str,
                  prompt_tokens: int, completion_tokens: int,
                  finish: str) -> None:
        self._asking = False
        self.on_query_busy(False)
        total = prompt_tokens + completion_tokens
        self.limiter.finish(ticket, total)
        usage = (f"Токены: {_fmt(total)} "
                 f"(вход {_fmt(prompt_tokens)}, выход {_fmt(completion_tokens)})")
        self.on_status(usage)
        if target != self.query_id:  # элемент сменился (например, база переоткрыта)
            return
        if finish == "length":
            self.on_answer("Ответ обрезан: достигнут MAX_OUTPUT_TOKENS. "
                           "Увеличьте значение в .env.\n\nСырой ответ:\n"
                           + (content or "(пусто)"))
            self.on_status("Ответ обрезан · " + usage)
            return
        try:
            self.on_answer(format_answer(content))
        except ValueError as exc:
            self.on_answer(f"Не удалось разобрать ответ ({exc}).\n\n"
                           f"Сырой ответ:\n{content or '(пусто)'}")
            self.on_status("Ответ не разобран · " + usage)

    def _on_failure(self, target: int, ticket: list, err: LlmError) -> None:
        self._asking = False
        self.on_query_busy(False)
        if err.kind != "rate":  # при 429 оставляем оценку: окно считаем осторожно
            self.limiter.finish(ticket, 0)
        if target != self.query_id:
            self.on_status(err.message)
            return
        self._query_error(err.message, err.detail)