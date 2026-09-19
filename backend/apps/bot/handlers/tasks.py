def on_done(client, account, callback_id: str, instance_id: int) -> None:
    """Button «Выполнено»: check_can_mark, then ask for a photo (awaiting_photo) or record the completion."""
    raise NotImplementedError


def on_photo(client, account, message: dict) -> None:
    """Photo for the task the employee is awaiting; attachment is {"type": "image", "payload": {"photo_id", "token", "url"}}."""
    raise NotImplementedError


def on_claim(client, account, callback_id: str, instance_id: int) -> None:
    """Button «Беру»: the first press wins, the rest of the shift is told who took it."""
    raise NotImplementedError


def on_status(client, account) -> None:
    """«Что осталось»: tasks of the employee's current shift, or the day-off / not-started / ended stub."""
    raise NotImplementedError
