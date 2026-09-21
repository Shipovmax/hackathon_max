from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction

from apps.core.domain.lifecycle import (
    ensure_instances,
    evaluate_status,
    planned_at,
    store_today,
    store_zone,
)
from apps.core.models import (
    EmployeeStatus,
    Shift,
    ShiftStatus,
    Store,
    TaskInstance,
    TaskStatus,
)

from . import board, keyboards, notifications, texts
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
    ).select_related("store", "employee__account", "employee__store")

    for shift in shifts:
        zone = store_zone(shift.store)
        starts_at = datetime.combine(shift.date, shift.start_time, tzinfo=zone)
        ends_at = datetime.combine(shift.date, shift.end_time, tzinfo=zone)
        if not starts_at <= now < ends_at:
            continue

        if sender is None:
            sender = MaxClient()
        # Доска смены: список задач и кнопка у каждой, отмечать можно прямо отсюда.
        board.send(sender, shift.employee, shift, now, texts.BOARD_SHIFT_STARTED)
        shift.start_notified_at = now
        shift.save(update_fields=["start_notified_at"])


def _claim_shifts(instance):
    return list(
        Shift.objects.filter(
            store=instance.template.store,
            date=instance.date,
            status=ShiftStatus.PUBLISHED,
            start_time__lte=instance.template.planned_time,
            end_time__gte=instance.template.planned_time,
            employee__status=EmployeeStatus.ACTIVE,
            employee__account__isnull=False,
        )
        .select_related("employee__account")
        .order_by("start_time", "employee__name")
    )


def send_claim_requests(now: datetime, client=None) -> None:
    """Ask the responsible shift who will take each claim task."""
    sender = client
    instances = TaskInstance.objects.filter(
        template__requires_claim=True,
        template__is_active=True,
        template__store__is_active=True,
        reminder_sent_at__isnull=True,
        claim__isnull=True,
        completion__isnull=True,
    ).select_related("template__store")

    for instance in instances:
        shifts = _claim_shifts(instance)
        if not shifts:
            continue
        zone = store_zone(instance.template.store)
        first_shift_start = min(
            datetime.combine(shift.date, shift.start_time, tzinfo=zone) for shift in shifts
        )
        if not first_shift_start <= now < planned_at(instance):
            continue
        if sender is None:
            sender = MaxClient()
        sent_to = set()
        for shift in shifts:
            user_id = shift.employee.account.max_user_id
            if user_id in sent_to:
                continue
            sent_to.add(user_id)
            sender.send_message(
                user_id=user_id,
                text=texts.claim_question(
                    instance.template.planned_time.strftime("%H:%M"),
                    instance.template.title,
                ),
                buttons=keyboards.claim_button(instance.id),
            )
        instance.reminder_sent_at = now
        instance.status = TaskStatus.REMINDED
        instance.save(update_fields=["reminder_sent_at", "status"])


def send_reminders(now: datetime, client=None) -> None:
    """
    Два напоминания перед сроком задачи: за REMINDER_FIRST и REMINDER_FINAL минут.

    Срок — плановое время плюс допуск задачи, то есть момент, когда она станет просроченной
    и о ней узнает владелец. Поэтому оба напоминания говорят, сколько осталось до него.
    """
    first_lead = timedelta(minutes=settings.REMINDER_FIRST_MINUTES_BEFORE)
    final_lead = timedelta(minutes=settings.REMINDER_FINAL_MINUTES_BEFORE)
    sender = client
    instances = TaskInstance.objects.filter(
        final_reminder_sent_at__isnull=True,
        completion__isnull=True,
        status__in=(TaskStatus.SCHEDULED, TaskStatus.REMINDED),
        template__is_active=True,
        template__requires_claim=False,
        template__store__is_active=True,
    ).select_related("template__store")

    for instance in instances:
        deadline = planned_at(instance) + timedelta(minutes=instance.template.tolerance_minutes)
        if now >= deadline:
            continue
        final = now >= deadline - final_lead
        if not final and (now < deadline - first_lead or instance.reminder_sent_at is not None):
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
        minutes_left = max(1, int((deadline - now).total_seconds() // 60))
        for user_id in recipient_ids:
            sender.send_message(
                user_id=user_id,
                text=texts.reminder(
                    instance.template.title,
                    instance.template.planned_time.strftime("%H:%M"),
                    deadline.strftime("%H:%M"),
                    minutes_left,
                    final,
                ),
                buttons=keyboards.done_button(instance.id),
            )

        # На последнем напоминании закрываем и первое: если бот лежал в его окно,
        # посылать «осталось 15 минут» задним числом уже незачем.
        instance.reminder_sent_at = instance.reminder_sent_at or now
        instance.status = TaskStatus.REMINDED
        fields = ["reminder_sent_at", "status"]
        if final:
            instance.final_reminder_sent_at = now
            fields.append("final_reminder_sent_at")
        instance.save(update_fields=fields)


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
                TaskInstance.objects.select_for_update(of=("self",))
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


def mark_overdue(now: datetime, client=None) -> None:
    """Move tasks past planned time + tolerance to overdue and notify the owner once."""
    sender = client
    candidate_ids = TaskInstance.objects.filter(
        overdue_notified_at__isnull=True,
        completion__isnull=True,
        template__is_active=True,
        template__requires_claim=False,
        template__store__is_active=True,
    ).values_list("id", flat=True)

    for instance_id in candidate_ids:
        with transaction.atomic():
            # PostgreSQL refuses FOR UPDATE over the nullable side of an outer join, and
            # select_related on completion/claim produces exactly that: lock only the row.
            instance = (
                TaskInstance.objects.select_for_update(of=("self",))
                .select_related(
                    "template__store__network__owner",
                    "completion",
                    "claim",
                )
                .filter(
                    pk=instance_id,
                    overdue_notified_at__isnull=True,
                    completion__isnull=True,
                )
                .first()
            )
            if instance is None or evaluate_status(instance, now) != TaskStatus.OVERDUE:
                continue
            if sender is None:
                sender = MaxClient()
            notifications.notify_owner_overdue(instance, client=sender)
            instance.status = TaskStatus.OVERDUE
            instance.overdue_notified_at = now
            instance.awaiting_photo_employee = None
            instance.awaiting_photo_since = None
            instance.save(
                update_fields=[
                    "status",
                    "overdue_notified_at",
                    "awaiting_photo_employee",
                    "awaiting_photo_since",
                ]
            )


def send_closing_notifications(now: datetime, client=None) -> None:
    """Tell the owner once when a previously reported overdue task is completed."""
    sender = client
    candidate_ids = TaskInstance.objects.filter(
        overdue_notified_at__isnull=False,
        closing_notified_at__isnull=True,
        completion__isnull=False,
    ).values_list("id", flat=True)

    for instance_id in candidate_ids:
        with transaction.atomic():
            instance = (
                TaskInstance.objects.select_for_update(of=("self",))
                .select_related(
                    "template__store__network__owner",
                    "completion__employee",
                )
                .filter(
                    pk=instance_id,
                    overdue_notified_at__isnull=False,
                    closing_notified_at__isnull=True,
                    completion__isnull=False,
                )
                .first()
            )
            if instance is None:
                continue
            if sender is None:
                sender = MaxClient()
            notifications.notify_owner_closed_late(instance, client=sender)
            instance.closing_notified_at = now
            instance.save(update_fields=["closing_notified_at"])


def escalate_unclaimed(now: datetime, client=None) -> None:
    """Claim tasks: repeat the question CLAIM_ESCALATION_MINUTES_BEFORE minutes before, tell the owner at the deadline."""
    sender = client
    instance_ids = TaskInstance.objects.filter(
        template__requires_claim=True,
        template__is_active=True,
        template__store__is_active=True,
        claim__isnull=True,
        completion__isnull=True,
    ).values_list("id", flat=True)
    escalation_delta = timedelta(minutes=settings.CLAIM_ESCALATION_MINUTES_BEFORE)

    for instance_id in instance_ids:
        with transaction.atomic():
            instance = (
                TaskInstance.objects.select_for_update(of=("self",))
                .select_related(
                    "template__store__network__owner",
                    "claim",
                    "completion",
                )
                .filter(
                    pk=instance_id,
                    claim__isnull=True,
                    completion__isnull=True,
                )
                .first()
            )
            if instance is None:
                continue
            if instance.date != store_today(instance.template.store, now):
                continue
            planned = planned_at(instance)
            if now >= planned:
                if instance.overdue_notified_at is not None:
                    continue
                if sender is None:
                    sender = MaxClient()
                notifications.notify_owner_unclaimed(instance, client=sender)
                instance.status = TaskStatus.UNCLAIMED
                instance.overdue_notified_at = now
                instance.save(update_fields=["status", "overdue_notified_at"])
                continue
            if now < planned - escalation_delta or instance.escalation_sent_at is not None:
                continue
            shifts = _claim_shifts(instance)
            if not shifts:
                continue
            if sender is None:
                sender = MaxClient()
            sent_to = set()
            for shift in shifts:
                user_id = shift.employee.account.max_user_id
                if user_id in sent_to:
                    continue
                sent_to.add(user_id)
                sender.send_message(
                    user_id=user_id,
                    text=texts.claim_escalation(
                        instance.template.title,
                        instance.template.planned_time.strftime("%H:%M"),
                        settings.CLAIM_ESCALATION_MINUTES_BEFORE,
                    ),
                    buttons=keyboards.claim_button(instance.id),
                )
            instance.escalation_sent_at = now
            instance.save(update_fields=["escalation_sent_at"])


def send_shift_summaries(now: datetime, client=None) -> None:
    """Shift-end summary «Выполнено N из M» for tasks that belonged to that employee's shift."""
    sender = client
    shift_ids = Shift.objects.filter(
        status=ShiftStatus.PUBLISHED,
        summary_sent_at__isnull=True,
        store__is_active=True,
        employee__status=EmployeeStatus.ACTIVE,
        employee__account__isnull=False,
    ).values_list("id", flat=True)
    boundary_tolerance = timedelta(minutes=settings.SHIFT_BOUNDARY_TOLERANCE_MINUTES)

    for shift_id in shift_ids:
        with transaction.atomic():
            shift = (
                Shift.objects.select_for_update(of=("self",))
                .select_related("store", "employee__account")
                .filter(
                    pk=shift_id,
                    status=ShiftStatus.PUBLISHED,
                    summary_sent_at__isnull=True,
                )
                .first()
            )
            if shift is None or shift.date != store_today(shift.store, now):
                continue
            ends_at = datetime.combine(
                shift.date,
                shift.end_time,
                tzinfo=store_zone(shift.store),
            )
            if now < ends_at + boundary_tolerance:
                continue

            relevant = []
            for instance in ensure_instances(shift.store, shift.date):
                planned_time = instance.template.planned_time
                if not shift.start_time <= planned_time <= shift.end_time:
                    continue
                claim = getattr(instance, "claim", None)
                if instance.template.requires_claim and (
                    claim is None or claim.employee_id != shift.employee_id
                ):
                    continue
                relevant.append(instance)

            done = [instance for instance in relevant if getattr(instance, "completion", None)]
            not_marked = [
                instance.template.title
                for instance in relevant
                if getattr(instance, "completion", None) is None
            ]
            if sender is None:
                sender = MaxClient()
            sender.send_message(
                user_id=shift.employee.account.max_user_id,
                text=texts.shift_summary(len(done), len(relevant), not_marked),
            )
            shift.summary_sent_at = now
            shift.save(update_fields=["summary_sent_at"])


def tick(now: datetime) -> None:
    generate_task_instances(now)
    send_shift_start_messages(now)
    send_claim_requests(now)
    send_reminders(now)
    expire_photo_waits(now)
    mark_overdue(now)
    send_closing_notifications(now)
    escalate_unclaimed(now)
    send_shift_summaries(now)
