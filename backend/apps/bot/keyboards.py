from django.conf import settings


def callback_button(text: str, payload: str) -> dict:
    return {"type": "callback", "text": text, "payload": payload}


def parse_callback(payload: str) -> tuple[str, str]:
    action, _, arg = (payload or "").partition(":")
    return action, arg


def role_choice() -> list[list[dict]]:
    return [
        [
            callback_button("Я владелец", "role:owner"),
            callback_button("Я сотрудник", "role:employee"),
        ]
    ]


def done_button(instance_id: int) -> list[list[dict]]:
    return [[callback_button("Выполнить", f"done:{instance_id}")]]


def claim_button(instance_id: int) -> list[list[dict]]:
    return [[callback_button("Беру", f"claim:{instance_id}")]]


MAX_TASK_BUTTONS = 28
BUTTON_TITLE_LIMIT = 30


def _short(title: str) -> str:
    return title if len(title) <= BUTTON_TITLE_LIMIT else title[: BUTTON_TITLE_LIMIT - 1] + "…"


def task_buttons(rows: list[tuple[int, str, str, bool]]) -> list[list[dict]]:
    buttons = []
    for instance_id, at, title, needs_claim in rows[:MAX_TASK_BUTTONS]:
        if needs_claim:
            buttons.append([callback_button(f"Беру · {at} {_short(title)}", f"claim:{instance_id}")])
        else:
            buttons.append([callback_button(f"Выполнить · {at} {_short(title)}", f"done:{instance_id}")])
    return buttons


def miniapp_link(start_param: str = "") -> str:
    suffix = f"={start_param}" if start_param else ""
    return f"https://max.ru/{settings.BOT_USERNAME}?startapp{suffix}"


def open_app(start_param: str = "") -> list[list[dict]]:
    return [[{"type": "link", "text": "Открыть приложение", "url": miniapp_link(start_param)}]]
