from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.core.domain.lifecycle import (
    ensure_instances,
    evaluate_status,
    planned_at,
    store_today,
    store_zone,
)
from apps.core.domain.permissions import shift_open_until
from apps.core.models import (
    EmployeeStatus,
    Shift,
    ShiftStatus,
    Store,
    TaskInstance,
    TaskKind,
    TaskStatus,
    TaskTemplate,
)

from . import board, keyboards, notifications, texts
from .max_api.client import MaxClient, message_id_of


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


def refresh_changed_boards(now: datetime, client=None) -> None:
    """
    Владелец правил задачи точки среди дня — присылаем смене обновлённый список.

    Смотрим только на задачи, попадающие в смену: правка вечерней задачи не должна
    дёргать утреннюю смену. Снятая галочка «активна» тоже двигает `updated_at`,
    поэтому удалённая задача уходит из списка вместе со своей кнопкой.
    """
    sender = client
    for shift in Shift.objects.filter(
        status=ShiftStatus.PUBLISHED,
        board_sent_at__isnull=False,
        store__is_active=True,
        employee__status=EmployeeStatus.ACTIVE,
        employee__account__isnull=False,
    ).select_related("store", "employee__account", "employee__store"):
        if not board.is_running(shift, now):
            continue
        changed = TaskTemplate.objects.filter(
            Q(kind=TaskKind.DAILY) | Q(on_date=shift.date),
            store=shift.store,
            updated_at__gt=shift.board_sent_at,
            planned_time__gte=shift.start_time,
            planned_time__lte=shift.end_time,
        ).exists()
        if not changed:
            continue
        if sender is None:
            sender = MaxClient()
        board.send(sender, shift.employee, shift, now, texts.BOARD_UPDATED)


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


def _remember_claim_prompt(instance, response) -> None:
    """Копим id сообщений с кнопкой «Беру»: по ним потом уберём кнопку."""
    message_id = message_id_of(response)
    if message_id:
        instance.claim_prompt_mids = [*instance.claim_prompt_mids, message_id]


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
            response = sender.send_message(
                user_id=user_id,
                text=texts.claim_question(
                    instance.template.planned_time.strftime("%H:%M"),
                    instance.template.title,
                ),
                buttons=keyboards.claim_button(instance.id),
            )
            _remember_claim_prompt(instance, response)
        instance.reminder_sent_at = now
        instance.status = TaskStatus.REMINDED
        instance.save(update_fields=["reminder_sent_at", "status", "claim_prompt_mids"])


def send_reminders(now: datetime, client=None) -> None:
    """
    Четыре напоминания: два перед плановым временем и два перед сроком задачи.

    Для каждой границы отправляем сообщения за REMINDER_FIRST и REMINDER_FINAL минут.
    Две временные отметки переиспользуются для обеих пар: время до planned_at означает,
    что отправлена плановая пара, время начиная с planned_at — что отправлена пара до срока.
    """
    first_lead = timedelta(minutes=settings.REMINDER_FIRST_MINUTES_BEFORE)
    final_lead = timedelta(minutes=settings.REMINDER_FINAL_MINUTES_BEFORE)
    sender = client
    instances = TaskInstance.objects.filter(
        completion__isnull=True,
        status__in=(TaskStatus.SCHEDULED, TaskStatus.REMINDED),
        template__is_active=True,
        template__requires_claim=False,
        template__store__is_active=True,
    ).select_related("template__store")

    for instance in instances:
        planned = planned_at(instance)
        deadline = planned + timedelta(minutes=instance.template.tolerance_minutes)
        if now >= deadline:
            continue

        stages = (
            (planned - first_lead, planned, False, "planned"),
            (planned - final_lead, planned, True, "planned"),
            (deadline - first_lead, deadline, False, "deadline"),
            (deadline - final_lead, deadline, True, "deadline"),
        )
        due_stages = [stage for stage in stages if stage[0] <= now < stage[1]]
        if not due_stages:
            continue

        _, target, final, phase = max(due_stages, key=lambda stage: stage[0])
        marker = instance.final_reminder_sent_at if final else instance.reminder_sent_at
        phase_sent = marker is not None and (
            (phase == "planned" and marker < planned)
            or (phase == "deadline" and marker >= planned)
        )
        if phase_sent:
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
        minutes_left = max(1, int((target - now).total_seconds() // 60))
        for user_id in recipient_ids:
            if phase == "planned":
                message = texts.planned_time_reminder(
                    instance.template.title,
                    instance.template.planned_time.strftime("%H:%M"),
                    minutes_left,
                    final,
                )
            else:
                message = texts.reminder(
                    instance.template.title,
                    instance.template.planned_time.strftime("%H:%M"),
                    deadline.strftime("%H:%M"),
                    minutes_left,
                    final,
                )
            sender.send_message(
                user_id=user_id,
                text=message,
                buttons=keyboards.done_button(instance.id),
            )

        # На втором напоминании каждой пары закрываем и первое: если бот лежал в его
        # окно, посылать запоздалое «осталось 15 минут» уже незачем.
        if not final or instance.reminder_sent_at is None or (
            phase == "deadline" and instance.reminder_sent_at < planned
        ):
            instance.reminder_sent_at = now
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
            # Повтор имеет смысл, только если первый вопрос ушёл до открытия этого окна.
            # Задачу могли создать за пару минут до срока — тогда «ещё никто не взял»
            # прилетело бы сразу следом за «Кто принимает?».
            if instance.reminder_sent_at is None or instance.reminder_sent_at >= planned - escalation_delta:
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
                response = sender.send_message(
                    user_id=user_id,
                    text=texts.claim_escalation(
                        instance.template.title,
                        instance.template.planned_time.strftime("%H:%M"),
                        settings.CLAIM_ESCALATION_MINUTES_BEFORE,
                    ),
                    buttons=keyboards.claim_button(instance.id),
                )
                _remember_claim_prompt(instance, response)
            instance.escalation_sent_at = now
            instance.save(update_fields=["escalation_sent_at", "claim_prompt_mids"])


# Итог смены, не отправленный за полсуток, уже никому не нужен: бот лежал, смена прошла.
SUMMARY_STALE_AFTER = timedelta(hours=12)


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
            if shift is None:
                continue
            # Итог — когда смене уже нечего отмечать: после срока её последней задачи.
            # Такой срок может перевалить за полночь, поэтому сверяем не дату, а окно.
            open_until = shift_open_until(shift)
            if not open_until <= now < open_until + SUMMARY_STALE_AFTER:
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
    refresh_changed_boards(now)
    send_claim_requests(now)
    send_reminders(now)
    expire_photo_waits(now)
    mark_overdue(now)
    send_closing_notifications(now)
    escalate_unclaimed(now)
    send_shift_summaries(now)
