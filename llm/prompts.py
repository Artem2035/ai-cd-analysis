"""Шаблон запроса, системный промт, схема ответа и вывод ответа в текст."""
import json

from data.format import format_size
from data.models import FileEntry

QUERY_TEMPLATE = (
    "Что это за объект ({kind}) и безопасно ли его удалить?\n"
    "Имя: {name}\n"
    "Путь: {path}\n"
    "Размер: {size}\n"
    "Изменён: {modified}"
)

SYSTEM_PROMPT = (
    "Ты эксперт по Windows и файлам на диске. Пользователь присылает имя, "
    "путь, размер и дату файла или папки. Ответь ТОЛЬКО JSON-объектом на "
    "русском языке с полями: what_is (что это), purpose (за что отвечает и "
    "что делает), can_delete (yes, no, depends или unknown), risk (риски "
    "удаления), safe_steps (до 5 коротких шагов безопасного удаления: "
    "резервная копия, перемещение в карантин, проверка; пустой список, если "
    "удалять нельзя), confidence (low, medium или high). Оценивай "
    "консервативно: если не уверен, ставь unknown и low. Системные папки и "
    "файлы Windows, драйверы и данные установленных программ помечай no. "
    "Будь краток: каждое текстовое поле одно-два предложения."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "what_is": {"type": "string"},
        "purpose": {"type": "string"},
        "can_delete": {"type": "string",
                       "enum": ["yes", "no", "depends", "unknown"]},
        "risk": {"type": "string"},
        "safe_steps": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["what_is", "purpose", "can_delete", "risk",
                 "safe_steps", "confidence"],
    "additionalProperties": False,
}
# Текст схемы нужен контроллеру для грубой оценки размера запроса
SCHEMA_TEXT = json.dumps(RESPONSE_SCHEMA, ensure_ascii=False)

_CAN_DELETE = {"yes": "да", "no": "нет", "depends": "зависит от условий",
               "unknown": "не уверен"}
_CONFIDENCE = {"low": "низкая", "medium": "средняя", "high": "высокая"}


def build_query(e: FileEntry) -> str:
    """Подставляет данные выбранного элемента в шаблон."""
    return QUERY_TEMPLATE.format(
        kind="папка" if e.is_dir else "файл",
        name=e.name, path=e.path,
        size=format_size(e.size), modified=e.modified or "—")


def _strip_fence(raw: str) -> str:
    """Некоторые модели оборачивают JSON в ```-блок."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def format_answer(raw: str) -> str:
    """JSON ответа -> читаемый текст. При ошибке разбора: ValueError."""
    try:
        data = json.loads(_strip_fence(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("неверный JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("ожидался JSON-объект")
    missing = [k for k in RESPONSE_SCHEMA["required"] if k not in data]
    if missing:
        raise ValueError("нет полей: " + ", ".join(missing))
    steps = data["safe_steps"]
    if not isinstance(steps, list):
        raise ValueError("safe_steps должен быть списком")

    can = _CAN_DELETE.get(data["can_delete"], str(data["can_delete"]))
    conf = _CONFIDENCE.get(data["confidence"], str(data["confidence"]))
    steps_text = ("\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
                  if steps else "—")
    return (f"Что это\n{data['what_is']}\n\n"
            f"Назначение\n{data['purpose']}\n\n"
            f"Можно удалить: {can}\n\n"
            f"Риски\n{data['risk']}\n\n"
            f"Как удалить безопаснее\n{steps_text}\n\n"
            f"Уверенность: {conf}")