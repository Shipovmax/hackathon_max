from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction

from apps.core.domain.lifecycle import ensure_instances, planned_at, store_today, store_zone
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


def send_shift_start_messages(now: datetime, client=None) -> None:
    """Message each employee whose published shift starts now with the task list."""
    sender = client
    shifts = Shift.objects.filter(
        status=ShiftStatus.PUBLISHED,
        start_notified_at__isnull=True,
        store__is_active=True,
        employee__status=EmployeeStatus.ACTIVE,
        employee__account__isnull=False,
    ).select_related("store", "employee__account")

    for shift in shifts:
        zone = store_zone(shift.store)
        starts_at = datetime.combine(shift.date, shift.start_time, tzinfo=zone)
        ends_at = datetime.combine(shift.date, shift.end_time, tzinfo=zone)
        if not starts_at <= now < ends_at:
            continue

        instances = ensure_instances(shift.store, shift.date)
        task_rows = [
            (instance.template.planned_time.strftime("%H:%M"), instance.template.title)
            for instance in sorted(
                instances,
                key=lambda item: item.template.planned_time,
            )
        ]
        if sender is None:
            sender = MaxClient()
        sender.send_message(
            user_id=shift.employee.account.max_user_id,
            text=texts.shift_started(
                shift.store.name,
                shift.end_time.strftime("%H:%M"),
                task_rows,
            ),
        )
        shift.start_notified_at = now
        shift.save(update_fields=["start_notified_at"])


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


def expire_photo_waits(now: datetime) -> None:
    """Release tasks whose employee did not send a photo within the configured timeout."""
    cutoff = now - timedelta(minutes=settings.PHOTO_WAIT_MINUTES)
    expired_ids = TaskInstance.objects.filter(
        status=TaskStatus.AWAITING_PHOTO,
        awaiting_photo_since__lte=cutoff,
    ).values_list("id", flat=True)

    for instance_id in expired_ids:
        with transaction.atomic():
            instance = (
                TaskInstance.objects.select_for_update()
                .filter(
                    pk=instance_id,
                    status=TaskStatus.AWAITING_PHOTO,
                    awaiting_photo_since__lte=cutoff,
                )
                .first()
            )
            if instance is None:
                continue
            instance.status = (
                TaskStatus.REMINDED if instance.reminder_sent_at else TaskStatus.SCHEDULED
            )
            instance.awaiting_photo_employee = None
            instance.awaiting_photo_since = None
            instance.save(
                update_fields=[
                    "status",
                    "awaiting_photo_employee",
                    "awaiting_photo_since",
                ]
            )


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
    expire_photo_waits(now)
    mark_overdue(now)
    escalate_unclaimed(now)
    send_shift_summaries(now)
