from datetime import datetime, timedelta

import httpx
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.domain.lifecycle import mark_done, store_today, store_zone
from apps.core.domain.permissions import MarkDenial, check_can_mark
from apps.core.models import (
    Employee,
    EmployeeStatus,
    Shift,
    ShiftStatus,
    TaskInstance,
    TaskStatus,
)

from .. import texts


def _time(value) -> str:
    return value.strftime("%H:%M")


def _next_shift_label(employee: Employee, now) -> str | None:
    today = store_today(employee.store, now)
    shifts = Shift.objects.filter(
        employee=employee,
        store=employee.store,
        status=ShiftStatus.PUBLISHED,
        date__gte=today,
    ).order_by("date", "start_time")
    zone = store_zone(employee.store)
    for shift in shifts:
        starts_at = datetime.combine(shift.date, shift.start_time, tzinfo=zone)
        if starts_at > now:
            if shift.date == today:
                day = "сегодня"
            elif shift.date == today + timedelta(days=1):
                day = "завтра"
            else:
                day = shift.date.strftime("%d.%m")
            return f"{day} с {_time(shift.start_time)}"
    return None


def _replacement_shift(employee: Employee, instance: TaskInstance, now):
    local_time = now.astimezone(store_zone(instance.template.store)).time().replace(tzinfo=None)
    return (
        Shift.objects.filter(
            store=instance.template.store,
            date=instance.date,
            status=ShiftStatus.PUBLISHED,
            employee__status=EmployeeStatus.ACTIVE,
        )
        .exclude(employee=employee)
        .filter(start_time__lte=local_time, end_time__gte=local_time)
        .select_related("employee")
        .order_by("start_time", "employee__name")
        .first()
    )


def _denial_text(employee: Employee, instance: TaskInstance, decision, now) -> str:
    title = instance.template.title
    if decision.denial == MarkDenial.DAY_OFF:
        return texts.denial_day_off(_next_shift_label(employee, now))
    if decision.denial == MarkDenial.NOT_STARTED:
        replacement = _replacement_shift(employee, instance, now)
        starts = replacement.start_time if replacement else decision.shift_start
        return texts.denial_not_started(_time(decision.shift_start), title, _time(starts))
    if decision.denial == MarkDenial.ENDED:
        replacement = _replacement_shift(employee, instance, now)
        who = replacement.employee.name if replacement else "следующая смена"
        return texts.denial_ended(_time(decision.shift_end), title, who)
    if decision.denial == MarkDenial.ALREADY_DONE:
        return texts.denial_already_done(title, decision.done_by, _time(decision.done_at))
    return texts.UNKNOWN


def _next_task_time(instance: TaskInstance, employee: Employee, now, shift_end) -> str | None:
    local_time = now.astimezone(store_zone(instance.template.store)).time().replace(tzinfo=None)
    next_instance = (
        TaskInstance.objects.filter(
            template__store=instance.template.store,
            template__is_active=True,
            date=instance.date,
            template__planned_time__gt=local_time,
            template__planned_time__lte=shift_end,
            completion__isnull=True,
        )
        .filter(Q(template__requires_claim=False) | Q(claim__employee=employee))
        .select_related("template")
        .order_by("template__planned_time")
        .first()
    )
    return _time(next_instance.template.planned_time) if next_instance else None


def on_done(client, account, callback_id: str, instance_id: int) -> None:
    """Check the employee's shift and either reserve a photo or record completion."""
    employee = (
        Employee.objects.filter(account=account, status=EmployeeStatus.ACTIVE)
        .select_related("store")
        .first()
    )
    if employee is None:
        client.answer_callback(callback_id, text=texts.ROLE_EMPLOYEE_ASK_CODE)
        return

    now = timezone.now()
    with transaction.atomic():
        instance = (
            TaskInstance.objects.select_for_update()
            .select_related(
                "template__store",
                "completion__employee",
                "awaiting_photo_employee",
            )
            .filter(pk=instance_id)
            .first()
        )
        if instance is None:
            response = texts.UNKNOWN
        else:
            decision = check_can_mark(employee, instance, now)
            if not decision.allowed:
                response = _denial_text(employee, instance, decision, now)
            elif (
                instance.status == TaskStatus.AWAITING_PHOTO
                and instance.awaiting_photo_employee_id
                and instance.awaiting_photo_employee_id != employee.id
            ):
                response = texts.awaiting_photo_by(
                    instance.template.title,
                    instance.awaiting_photo_employee.name,
                )
            elif (
                instance.status == TaskStatus.AWAITING_PHOTO
                and instance.awaiting_photo_employee_id == employee.id
            ):
                response = texts.ask_photo(instance.template.photo_prompt)
            elif instance.template.requires_photo:
                pending = (
                    TaskInstance.objects.filter(
                        status=TaskStatus.AWAITING_PHOTO,
                        awaiting_photo_employee=employee,
                    )
                    .exclude(pk=instance.pk)
                    .select_related("template")
                    .order_by("awaiting_photo_since")
                    .first()
                )
                if pending:
                    response = texts.finish_pending_photo(pending.template.title)
                else:
                    instance.status = TaskStatus.AWAITING_PHOTO
                    instance.awaiting_photo_employee = employee
                    instance.awaiting_photo_since = now
                    instance.save(
                        update_fields=[
                            "status",
                            "awaiting_photo_employee",
                            "awaiting_photo_since",
                        ]
                    )
                    response = texts.ask_photo(instance.template.photo_prompt)
            else:
                completion = mark_done(instance, employee, now)
                response = texts.marked(
                    instance.template.title,
                    _time(completion.completed_at.astimezone(store_zone(instance.template.store))),
                    _next_task_time(instance, employee, now, decision.shift_end),
                )

    client.answer_callback(callback_id, text=response)


def on_photo(client, account, message: dict) -> None:
    """Photo for the task the employee is awaiting; attachment has a CDN URL."""
    employee = (
        Employee.objects.filter(account=account, status=EmployeeStatus.ACTIVE)
        .select_related("store")
        .first()
    )
    if employee is None:
        client.send_message(user_id=account.max_user_id, text=texts.ROLE_EMPLOYEE_ASK_CODE)
        return

    pending = (
        TaskInstance.objects.filter(
            status=TaskStatus.AWAITING_PHOTO,
            awaiting_photo_employee=employee,
        )
        .select_related("template__store")
        .order_by("-awaiting_photo_since")
        .first()
    )
    if pending is None:
        client.send_message(user_id=account.max_user_id, text=texts.PHOTO_NOT_EXPECTED)
        return

    attachments = (message.get("body") or {}).get("attachments") or []
    image = next((item for item in attachments if item.get("type") == "image"), None)
    payload = (image or {}).get("payload") or {}
    url = payload.get("url")
    if not url:
        client.send_message(user_id=account.max_user_id, text=texts.PHOTO_FAILED)
        return

    try:
        photo = client.download_file(url)
    except (httpx.HTTPError, ValueError):
        client.send_message(user_id=account.max_user_id, text=texts.PHOTO_FAILED)
        return
    if not photo:
        client.send_message(user_id=account.max_user_id, text=texts.PHOTO_FAILED)
        return

    now = timezone.now()
    with transaction.atomic():
        instance = (
            TaskInstance.objects.select_for_update()
            .select_related("template__store", "completion")
            .filter(
                pk=pending.pk,
                status=TaskStatus.AWAITING_PHOTO,
                awaiting_photo_employee=employee,
            )
            .first()
        )
        if instance is None:
            response = texts.PHOTO_NOT_EXPECTED
        else:
            reserved_at = instance.awaiting_photo_since or now
            decision = check_can_mark(employee, instance, reserved_at)
            shift_end = decision.shift_end or instance.template.store.close_time
            completion = mark_done(
                instance,
                employee,
                now,
                photo=photo,
                photo_token=payload.get("token") or "",
            )
            response = texts.marked(
                instance.template.title,
                _time(completion.completed_at.astimezone(store_zone(instance.template.store))),
                _next_task_time(instance, employee, now, shift_end),
            )

    client.send_message(user_id=account.max_user_id, text=response)


def on_claim(client, account, callback_id: str, instance_id: int) -> None:
    """Button «Беру»: the first press wins, the rest of the shift is told who took it."""
    raise NotImplementedError


def on_status(client, account) -> None:
    """«Что осталось»: tasks of the current shift, or a shift-state stub."""
    raise NotImplementedError
