from datetime import datetime

from apps.core.domain.lifecycle import ensure_instances, store_today
from apps.core.models import Store


def generate_task_instances(now: datetime) -> None:
    """Create TaskInstance rows for today from active templates."""
    for store in Store.objects.filter(is_active=True).iterator():
        ensure_instances(store, store_today(store, now))


def send_shift_start_messages(now: datetime) -> None:
    """Message each employee whose published shift starts now with the task list."""


def send_reminders(now: datetime) -> None:
    """Reminder with the «Выполнено» button REMINDER_MINUTES_BEFORE minutes before the planned time."""


def mark_overdue(now: datetime) -> None:
    """Move tasks past planned time + tolerance to overdue and notify the owner once."""


def escalate_unclaimed(now: datetime) -> None:
    """Claim tasks: repeat the question CLAIM_ESCALATION_MINUTES_BEFORE minutes before, tell the owner at the deadline."""


def send_shift_summaries(now: datetime) -> None:
    """Shift-end summary «Выполнено N из M» for tasks that belonged to that employee's shift."""


def tick(now: datetime) -> None:
    generate_task_instances(now)
    send_shift_start_messages(now)
    send_reminders(now)
    mark_overdue(now)
    escalate_unclaimed(now)
    send_shift_summaries(now)
