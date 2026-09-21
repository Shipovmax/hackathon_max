"""
Доска смены: список задач сотрудника с кнопкой у каждой незакрытой задачи.

Одна и та же доска уходит в начале смены, после каждой отметки и на «что осталось».
Поэтому сотрудник всегда видит актуальный список, а не цепочку разрозненных сообщений,
и не может нажать кнопку задачи, которой в его смене нет.
"""

from dataclasses import dataclass
from datetime import date as date_type, datetime, timedelta

from django.conf import settings

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

from . import keyboards, texts

DONE_STATUSES = (TaskStatus.DONE_ON_TIME, TaskStatus.DONE_LATE)


def _hhmm(value) -> str:
    return value.strftime("%H:%M")


def deadline_at(instance: TaskInstance) -> datetime:
    """Момент, после которого задача считается просроченной."""
    return planned_at(instance) + timedelta(minutes=instance.template.tolerance_minutes)


def current_shift(employee, now: datetime) -> Shift | None:
    """Опубликованная смена сотрудника, идущая прямо сейчас, с допуском на границах."""
    store = employee.store
    zone = store_zone(store)
    tolerance = timedelta(minutes=settings.SHIFT_BOUNDARY_TOLERANCE_MINUTES)
    shifts = Shift.objects.filter(
        employee=employee,
        store=store,
        date=store_today(store, now),
        status=ShiftStatus.PUBLISHED,
    ).order_by("start_time")
    for shift in shifts:
        starts_at = datetime.combine(shift.date, shift.start_time, tzinfo=zone)
        ends_at = datetime.combine(shift.date, shift.end_time, tzinfo=zone)
        if starts_at - tolerance <= now <= ends_at + tolerance:
            return shift
    return None


def running_shifts(store: Store, day: date_type, now: datetime) -> list[Shift]:
    """Все, кто сейчас на смене в этой точке и подключён к боту."""
    zone = store_zone(store)
    tolerance = timedelta(minutes=settings.SHIFT_BOUNDARY_TOLERANCE_MINUTES)
    shifts = (
        Shift.objects.filter(
            store=store,
            date=day,
            status=ShiftStatus.PUBLISHED,
            employee__status=EmployeeStatus.ACTIVE,
            employee__account__isnull=False,
        )
        .select_related("employee__account")
        .order_by("start_time", "employee__name")
    )
    running = []
    for shift in shifts:
        starts_at = datetime.combine(shift.date, shift.start_time, tzinfo=zone)
        ends_at = datetime.combine(shift.date, shift.end_time, tzinfo=zone)
        if starts_at - tolerance <= now <= ends_at + tolerance:
            running.append(shift)
    return running


@dataclass(frozen=True)
class Row:
    instance: TaskInstance
    status: str

    @property
    def done(self) -> bool:
        return self.status in DONE_STATUSES


def rows_for(employee, shift: Shift, now: datetime) -> list[Row]:
    """
    Задачи смены: те, чьё плановое время попадает в её границы.

    Чужую задачу «Беру» не показываем — за неё отвечает тот, кто её взял, и упрекать
    за неё постороннего нельзя (CLAUDE.md §6).
    """
    rows = []
    for instance in ensure_instances(employee.store, shift.date):
        if not shift.start_time <= instance.template.planned_time <= shift.end_time:
            continue
        claim = getattr(instance, "claim", None)
        if instance.template.requires_claim and claim is not None and claim.employee_id != employee.id:
            continue
        rows.append(Row(instance, evaluate_status(instance, now)))
    return rows


def _describe(row: Row) -> tuple[str, str, str, str]:
    """Строка списка: значок, время, название, пояснение о текущем состоянии."""
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
    elif template.requires_claim and getattr(instance, "claim", None) is None:
        mark, note = "○", texts.board_row_claim_free(at)
    else:
        mark, note = "○", texts.board_row_open(deadline, template.requires_photo)
    return mark, at, template.title, note


def _button_rows(rows: list[Row]) -> list[tuple[int, str, str, bool]]:
    """Кнопки ставим только у задач, с которыми сотрудник может что-то сделать сейчас."""
    out = []
    for row in rows:
        if row.done or row.status == TaskStatus.MISSED:
            continue
        template = row.instance.template
        needs_claim = template.requires_claim and getattr(row.instance, "claim", None) is None
        out.append((row.instance.id, _hhmm(template.planned_time), template.title, needs_claim))
    return out


def build(employee, shift: Shift, now: datetime, heading: str) -> tuple[str, list[list[dict]]]:
    """Текст доски и клавиатура к ней."""
    rows = rows_for(employee, shift, now)
    text = texts.shift_board(
        heading,
        employee.store.name,
        _hhmm(shift.start_time),
        _hhmm(shift.end_time),
        [_describe(row) for row in rows],
        sum(1 for row in rows if row.done),
        len(rows),
    )
    return text, keyboards.task_buttons(_button_rows(rows))


def send(client, employee, shift: Shift, now: datetime, heading: str) -> None:
    text, buttons = build(employee, shift, now, heading)
    client.send_message(user_id=employee.account.max_user_id, text=text, buttons=buttons)


def broadcast(client, store: Store, day: date_type, now: datetime, heading: str, skip_employee_id: int) -> None:
    """
    Обновлённый список остальным, кто сейчас на смене.

    Тому, кто нажал кнопку, доска приходит ответом на нажатие и заменяет прежнее сообщение,
    поэтому его здесь пропускаем.
    """
    for shift in running_shifts(store, day, now):
        if shift.employee_id == skip_employee_id:
            continue
        send(client, shift.employee, shift, now, heading)
