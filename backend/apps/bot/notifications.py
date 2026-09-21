from apps.core.domain.lifecycle import planned_at, store_zone

from . import keyboards, texts
from .max_api.client import MaxClient


def _store_deep_link(instance) -> list[list[dict]]:
    payload = f"store_{instance.template.store_id}_{instance.date:%Y%m%d}"
    return keyboards.open_app(payload)


def notify_owner_overdue(instance, client=None) -> None:
    """Once per task when the tolerance expires without a completion (CLAUDE.md §5)."""
    store = instance.template.store
    sender = client or MaxClient()
    sender.send_message(
        user_id=store.network.owner.max_user_id,
        text=texts.owner_overdue(
            store.name,
            instance.template.title,
            planned_at(instance).strftime("%H:%M"),
        ),
        buttons=_store_deep_link(instance),
    )


def notify_owner_closed_late(instance, client=None) -> None:
    """Closing notification, sent once when an overdue task is finally completed."""
    store = instance.template.store
    completion = instance.completion
    sender = client or MaxClient()
    sender.send_message(
        user_id=store.network.owner.max_user_id,
        text=texts.owner_closed_late(
            store.name,
            instance.template.title,
            completion.completed_at.astimezone(store_zone(store)).strftime("%H:%M"),
            completion.late_minutes,
            completion.employee.name,
        ),
        buttons=_store_deep_link(instance),
    )


def notify_owner_unclaimed(instance) -> None:
    """«Задачу никто не взял»: a claim task nobody took by its planned time."""
    raise NotImplementedError
