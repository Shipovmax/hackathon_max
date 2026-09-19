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
    return [[callback_button("Выполнено", f"done:{instance_id}")]]


def claim_button(instance_id: int) -> list[list[dict]]:
    return [[callback_button("Беру", f"claim:{instance_id}")]]


def miniapp_link(start_param: str = "") -> str:
    """Deep link that opens the mini-app; start_param allows [A-Za-z0-9_-] up to 512 chars."""
    suffix = f"={start_param}" if start_param else ""
    return f"https://max.ru/{settings.BOT_USERNAME}?startapp{suffix}"


def open_app(start_param: str = "") -> list[list[dict]]:
    return [[{"type": "link", "text": "Открыть приложение", "url": miniapp_link(start_param)}]]
