import logging
from dataclasses import dataclass
from datetime import date as date_type, datetime, timedelta

import httpx
from django.conf import settings

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
    TaskStatus,
)

from . import keyboards, texts
from .max_api.client import MaxApiError

log = logging.getLogger(__name__)

DONE_STATUSES = (TaskStatus.DONE_ON_TIME, TaskStatus.DONE_LATE)


def _hhmm(value) -> str:
    return value.strftime("%H:%M")


def _shift_end(value) -> str:
    return "24:00" if (value.hour, value.minute) == (23, 59) else _hhmm(value)


def deadline_at(instance: TaskInstance) -> datetime:
    return planned_at(instance) + timedelta(minutes=instance.template.tolerance_minutes)


def is_open_yet(instance: TaskInstance, now: datetime) -> bool:
    zone = store_zone(instance.template.store)
    opens_at = datetime.combine(instance.date, instance.template.available_from, tzinfo=zone)
    return now >= opens_at


def is_running(shift: Shift, now: datetime) -> bool:
    zone = store_zone(shift.store)
    tolerance = timedelta(minutes=settings.SHIFT_BOUNDARY_TOLERANCE_MINUTES)
    starts_at = datetime.combine(shift.date, shift.start_time, tzinfo=zone)
    return starts_at - tolerance <= now <= shift_open_until(shift)


def current_shift(employee, now: datetime) -> Shift | None:
    shifts = (
        Shift.objects.filter(
            employee=employee,
            store=employee.store,
            date=store_today(employee.store, now),
            status=ShiftStatus.PUBLISHED,
        )
        .select_related("store")
        .order_by("start_time")
    )
    return next((shift for shift in shifts if is_running(shift, now)), None)


def running_shifts(store: Store, day: date_type, now: datetime) -> list[Shift]:
    shifts = (
        Shift.objects.filter(
            store=store,
            date=day,
            status=ShiftStatus.PUBLISHED,
            employee__status=EmployeeStatus.ACTIVE,
            employee__account__isnull=False,
        )
        .select_related("store", "employee__account", "employee__store")
        .order_by("start_time", "employee__name")
    )
    return [shift for shift in shifts if is_running(shift, now)]


@dataclass(frozen=True)
class Row:
    instance: TaskInstance
    status: str

    @property
    def done(self) -> bool:
        return self.status in DONE_STATUSES


def rows_for(employee, shift: Shift, now: datetime) -> list[Row]:
    rows = []
    for instance in ensure_instances(employee.store, shift.date):
        if not shift.start_time <= instance.template.planned_time <= shift.end_time:
            continue
        claim = getattr(instance, "claim", None)
        if instance.template.requires_claim and claim is not None and claim.employee_id != employee.id:
            continue
        rows.append(Row(instance, evaluate_status(instance, now)))
    return rows


def _describe(row: Row, now: datetime) -> tuple[str, str, str, str]:
    instance, template = row.instance, row.instance.template
    at = _hhmm(template.planned_time)
    deadline = _hhmm(deadline_at(instance))
    completion = getattr(instance, "completion", None)

    if row.done and completion is not None:
        mark = "✓"
        done_at = _hhmm(completion.completed_at.astimezone(store_zone(template.store)))
        late = completion.late_minutes if row.status == TaskStatus.DONE_LATE else 0
        note = texts.board_row_done(completion.employee.name, done_at, late)
    elif row.status == TaskStatus.AWAITING_PHOTO:
        mark = "…"
        who = instance.awaiting_photo_employee
        note = texts.board_row_awaiting(who.name if who else "сотрудника")
    elif row.status == TaskStatus.OVERDUE:
        mark, note = "⚠", texts.board_row_overdue(deadline)
    elif row.status == TaskStatus.MISSED:
        mark, note = "⚠", texts.BOARD_ROW_MISSED
    elif row.status == TaskStatus.UNCLAIMED:
        mark, note = "⚠", texts.board_row_unclaimed(at)
    elif not is_open_yet(instance, now):
        mark, note = "·", texts.board_row_not_yet(_hhmm(template.available_from))
    elif template.requires_claim and getattr(instance, "claim", None) is None:
        mark, note = "○", texts.board_row_claim_free(at)
    else:
        mark, note = "○", texts.board_row_open(deadline, template.requires_photo)
    return mark, at, template.title, note


def _button_rows(rows: list[Row], now: datetime) -> list[tuple[int, str, str, bool]]:
    out = []
    for row in rows:
        if row.done or row.status == TaskStatus.MISSED:
            continue
        if not is_open_yet(row.instance, now):
            continue
        template = row.instance.template
        needs_claim = template.requires_claim and getattr(row.instance, "claim", None) is None
        out.append((row.instance.id, _hhmm(template.planned_time), template.title, needs_claim))
    return out


def build(employee, shift: Shift, now: datetime, heading: str) -> tuple[str, list[list[dict]]]:
    rows = rows_for(employee, shift, now)
    text = texts.shift_board(
        heading,
        employee.store.name,
        _hhmm(shift.start_time),
        _shift_end(shift.end_time),
        [_describe(row, now) for row in rows],
        sum(1 for row in rows if row.done),
        len(rows),
    )
    return text, keyboards.task_buttons(_button_rows(rows, now))


def mark_shown(shift: Shift, now: datetime) -> None:
    shift.board_sent_at = now
    shift.save(update_fields=["board_sent_at"])


def send(client, employee, shift: Shift, now: datetime, heading: str) -> None:
    text, buttons = build(employee, shift, now, heading)
    client.send_message(user_id=employee.account.max_user_id, text=text, buttons=buttons)
    mark_shown(shift, now)


def broadcast(client, store: Store, day: date_type, now: datetime, heading: str, skip_employee_id: int) -> None:
    for shift in running_shifts(store, day, now):
        if shift.employee_id == skip_employee_id:
            continue
        try:
            send(client, shift.employee, shift, now, heading)
        except (MaxApiError, httpx.HTTPError) as error:
            log.warning("не удалось отправить доску смены %s: %s", shift.id, error)
