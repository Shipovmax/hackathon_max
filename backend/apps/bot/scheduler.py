from datetime import datetime, timedelta

from django.conf import settings

from apps.core.domain.lifecycle import ensure_instances, planned_at, store_today
from apps.core.models import (
    EmployeeStatus,
    Shift,
    ShiftStatus,
    Store,
    TaskInstance,
    TaskStatus,
)

from . import keyboards, texts
from .max_api.client import MaxClient


def generate_task_instances(now: datetime) -> None:
    """Create TaskInstance rows for today from active templates."""
    for store in Store.objects.filter(is_active=True).iterator():
        ensure_instances(store, store_today(store, now))


def send_shift_start_messages(now: datetime) -> None:
    """Message each employee whose published shift starts now with the task list."""


def send_reminders(now: datetime, client=None) -> None:
    """Reminder with the «Выполнено» button REMINDER_MINUTES_BEFORE minutes before the planned time."""
    lead_time = timedelta(minutes=settings.REMINDER_MINUTES_BEFORE)
    sender = client
    instances = TaskInstance.objects.filter(
        reminder_sent_at__isnull=True,
        status=TaskStatus.SCHEDULED,
        template__is_active=True,
        template__store__is_active=True,
    ).select_related("template__store")

    for instance in instances:
        planned = planned_at(instance)
        if not planned - lead_time <= now < planned:
            continue

        recipient_ids = list(
            Shift.objects.filter(
                store=instance.template.store,
                date=instance.date,
                status=ShiftStatus.PUBLISHED,
                start_time__lte=instance.template.planned_time,
                end_time__gte=instance.template.planned_time,
                employee__status=EmployeeStatus.ACTIVE,
                employee__account__isnull=False,
            )
            .order_by()
            .values_list("employee__account__max_user_id", flat=True)
            .distinct()
        )
        if not recipient_ids:
            continue

        if sender is None:
            sender = MaxClient()
        for user_id in recipient_ids:
            sender.send_message(
                user_id=user_id,
                text=texts.reminder(settings.REMINDER_MINUTES_BEFORE, instance.template.title),
                buttons=keyboards.done_button(instance.id),
            )

        instance.reminder_sent_at = now
        instance.status = TaskStatus.REMINDED
        instance.save(update_fields=["reminder_sent_at", "status"])


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
