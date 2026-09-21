from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.domain.lifecycle import mark_done, store_today, store_zone
from apps.core.domain.permissions import MarkDenial, check_can_mark
from apps.core.models import (
    Claim,
    Employee,
    EmployeeStatus,
    Shift,
    ShiftStatus,
    TaskInstance,
    TaskStatus,
)

from .. import board, texts


def _time(value) -> str:
    return value.strftime("%H:%M")


def _employee(account) -> Employee | None:
    return (
        Employee.objects.filter(account=account, status=EmployeeStatus.ACTIVE)
        .select_related("store")
        .first()
    )


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


def _late(instance: TaskInstance, completion) -> int:
    """Опоздание показываем, только если оно вышло за допуск задачи."""
    return completion.late_minutes if instance.status == TaskStatus.DONE_LATE else 0


def _photo_request(instance: TaskInstance) -> str:
    """Просьба о фото называет задачу и срок: кнопок в смене несколько, они похожи."""
    return texts.ask_photo_for(
        instance.template.title,
        _time(instance.template.planned_time),
        _time(board.deadline_at(instance)),
        settings.PHOTO_WAIT_MINUTES,
        instance.template.photo_prompt,
    )


def _answer_with_board(client, callback_id: str, employee: Employee, now, heading: str) -> None:
    """
    Ответ на нажатие заменяет сообщение с кнопкой, поэтому кладём туда всю доску:
    сотрудник сразу видит обновлённый список, а не состояние до нажатия.
    """
    shift = board.current_shift(employee, now)
    if shift is None:
        client.answer_callback(callback_id, text=heading)
        return
    text, buttons = board.build(employee, shift, now, heading)
    client.answer_callback(callback_id, text=text, buttons=buttons)


def _tell_the_rest(client, employee: Employee, instance: TaskInstance, now, heading: str) -> None:
    """Остальным на смене — обновлённый список, чтобы никто не делал работу дважды."""
    board.broadcast(
        client,
        instance.template.store,
        instance.date,
        now,
        heading,
        skip_employee_id=employee.id,
    )


@dataclass
class _Outcome:
    """Чем закончилось нажатие «Выполнено»: отказ, просьба о фото или готовая отметка."""

    kind: str  # refused | photo | done
    text: str = ""
    instance: TaskInstance | None = None
    done_at: str = ""
    late_minutes: int = 0


def _mark_or_refuse(employee: Employee, instance_id: int, now) -> _Outcome:
    with transaction.atomic():
        instance = (
            TaskInstance.objects.select_for_update(of=("self",))
            .select_related(
                "template__store",
                "completion__employee",
                "claim__employee",
                "awaiting_photo_employee",
            )
            .filter(pk=instance_id)
            .first()
        )
        if instance is None:
            return _Outcome("refused", texts.UNKNOWN)

        template = instance.template
        claim = getattr(instance, "claim", None)
        if template.requires_claim and claim is None:
            return _Outcome("refused", texts.CLAIM_REQUIRED)
        if template.requires_claim and claim.employee_id != employee.id:
            return _Outcome(
                "refused",
                texts.claim_taken_by(template.title, _time(template.planned_time), claim.employee.name),
            )

        decision = check_can_mark(employee, instance, now)
        if not decision.allowed:
            return _Outcome("refused", _denial_text(employee, instance, decision, now))

        if instance.status == TaskStatus.AWAITING_PHOTO and instance.awaiting_photo_employee_id:
            if instance.awaiting_photo_employee_id != employee.id:
                return _Outcome(
                    "refused",
                    texts.awaiting_photo_by(template.title, instance.awaiting_photo_employee.name),
                )
            return _Outcome("photo", _photo_request(instance), instance=instance)

        if template.requires_photo:
            # Одно ожидание фото на сотрудника: иначе непонятно, к какой задаче снимок.
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
                return _Outcome("refused", texts.finish_pending_photo(pending.template.title))
            instance.status = TaskStatus.AWAITING_PHOTO
            instance.awaiting_photo_employee = employee
            instance.awaiting_photo_since = now
            instance.save(
                update_fields=["status", "awaiting_photo_employee", "awaiting_photo_since"]
            )
            return _Outcome("photo", _photo_request(instance), instance=instance)

        completion = mark_done(instance, employee, now)
        return _Outcome(
            "done",
            instance=instance,
            done_at=_time(completion.completed_at.astimezone(store_zone(template.store))),
            late_minutes=_late(instance, completion),
        )


def on_done(client, account, callback_id: str, instance_id: int) -> None:
    """Кнопка «Выполнено»: проверяет смену и либо просит фото, либо закрывает задачу."""
    employee = _employee(account)
    if employee is None:
        client.answer_callback(callback_id, text=texts.ROLE_EMPLOYEE_ASK_CODE)
        return

    now = timezone.now()
    result = _mark_or_refuse(employee, instance_id, now)

    if result.kind == "photo":
        # Ждём одно конкретное действие, поэтому список с кнопками сейчас только мешает.
        client.answer_callback(callback_id, text=result.text)
        return
    if result.kind == "refused":
        _answer_with_board(client, callback_id, employee, now, result.text)
        return

    instance = result.instance
    _answer_with_board(
        client,
        callback_id,
        employee,
        now,
        texts.done_heading(instance.template.title, result.done_at, result.late_minutes),
    )
    _tell_the_rest(
        client,
        employee,
        instance,
        now,
        texts.done_by_other_heading(instance.template.title, employee.name, result.done_at),
    )


def on_photo(client, account, message: dict) -> None:
    """Фото для задачи, которую сотрудник взял на отметку; вложение несёт ссылку на CDN."""
    employee = _employee(account)
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
    heading = None
    with transaction.atomic():
        instance = (
            TaskInstance.objects.select_for_update(of=("self",))
            .select_related("template__store", "completion")
            .filter(
                pk=pending.pk,
                status=TaskStatus.AWAITING_PHOTO,
                awaiting_photo_employee=employee,
            )
            .first()
        )
        if instance is not None:
            completion = mark_done(
                instance,
                employee,
                now,
                photo=photo,
                photo_token=payload.get("token") or "",
            )
            done_at = _time(completion.completed_at.astimezone(store_zone(instance.template.store)))
            heading = texts.photo_accepted_heading(
                instance.template.title, done_at, _late(instance, completion)
            )

    if heading is None:
        client.send_message(user_id=account.max_user_id, text=texts.PHOTO_NOT_EXPECTED)
        return

    shift = board.current_shift(employee, now)
    if shift is None:
        client.send_message(user_id=account.max_user_id, text=heading)
    else:
        board.send(client, employee, shift, now, heading)
    _tell_the_rest(
        client,
        employee,
        instance,
        now,
        texts.done_by_other_heading(instance.template.title, employee.name, done_at),
    )


def on_claim(client, account, callback_id: str, instance_id: int) -> None:
    """Кнопка «Беру»: первое нажатие побеждает, остальным на смене говорим, кто взял."""
    employee = _employee(account)
    if employee is None:
        client.answer_callback(callback_id, text=texts.ROLE_EMPLOYEE_ASK_CODE)
        return

    now = timezone.now()
    taken = False
    with transaction.atomic():
        instance = (
            TaskInstance.objects.select_for_update(of=("self",))
            .select_related("template__store", "claim__employee")
            .filter(pk=instance_id)
            .first()
        )
        if instance is None or not instance.template.requires_claim:
            response = texts.UNKNOWN
        elif (
            not instance.template.is_active
            or not instance.template.store.is_active
            or instance.date != store_today(instance.template.store, now)
        ):
            response = texts.CLAIM_NOT_AVAILABLE
        else:
            claim = getattr(instance, "claim", None)
            if claim is not None:
                if claim.employee_id == employee.id:
                    response = texts.claimed_heading(
                        instance.template.title, _time(instance.template.planned_time)
                    )
                else:
                    response = texts.claim_taken_by(
                        instance.template.title,
                        _time(instance.template.planned_time),
                        claim.employee.name,
                    )
            else:
                eligible = Shift.objects.filter(
                    employee=employee,
                    store=instance.template.store,
                    date=instance.date,
                    status=ShiftStatus.PUBLISHED,
                    start_time__lte=instance.template.planned_time,
                    end_time__gte=instance.template.planned_time,
                ).exists()
                if not eligible:
                    response = texts.CLAIM_NOT_AVAILABLE
                else:
                    Claim.objects.create(instance=instance, employee=employee)
                    response = texts.claimed_heading(
                        instance.template.title, _time(instance.template.planned_time)
                    )
                    taken = True

    _answer_with_board(client, callback_id, employee, now, response)
    if taken:
        _tell_the_rest(
            client,
            employee,
            instance,
            now,
            texts.claim_taken_by(
                instance.template.title,
                _time(instance.template.planned_time),
                employee.name,
            ),
        )


def on_status(client, account) -> None:
    """«Что осталось»: доска текущей смены или заглушка про состояние смены."""
    employee = _employee(account)
    if employee is None:
        client.send_message(user_id=account.max_user_id, text=texts.ROLE_EMPLOYEE_ASK_CODE)
        return

    now = timezone.now()
    store = employee.store
    day = store_today(store, now)
    zone = store_zone(store)
    tolerance = timedelta(minutes=settings.SHIFT_BOUNDARY_TOLERANCE_MINUTES)
    shifts = list(
        Shift.objects.filter(
            employee=employee,
            store=store,
            date=day,
            status=ShiftStatus.PUBLISHED,
        ).order_by("start_time")
    )

    def bounds(shift):
        starts_at = datetime.combine(shift.date, shift.start_time, tzinfo=zone)
        ends_at = datetime.combine(shift.date, shift.end_time, tzinfo=zone)
        return starts_at - tolerance, ends_at + tolerance

    current = next((shift for shift in shifts if bounds(shift)[0] <= now <= bounds(shift)[1]), None)
    if current is None:
        upcoming = [shift for shift in shifts if now < bounds(shift)[0]]
        if upcoming:
            response = texts.status_not_started(_time(upcoming[0].start_time))
        elif shifts:
            response = texts.status_ended(_time(shifts[-1].end_time))
        else:
            response = texts.denial_day_off(_next_shift_label(employee, now))
        client.send_message(user_id=account.max_user_id, text=response)
        return

    board.send(client, employee, current, now, texts.BOARD_STATUS)
