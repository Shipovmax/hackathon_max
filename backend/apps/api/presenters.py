"""Response shapes for the mini-app. They mirror frontend/src/api/types.ts."""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.core.domain.coverage import find_gaps
from apps.core.domain.day import DayTaskRow
from apps.core.models import (
    Employee,
    EmployeeStatus,
    Shift,
    ShiftStatus,
    Store,
    TaskTemplate,
)

from .scoping import hhmm


def person(employee: Employee) -> dict:
    if employee.status == EmployeeStatus.DISMISSED:
        return {"id": employee.id, "name": employee.name, "status": "dismissed", "invite_code": None}
    if employee.account_id:
        return {"id": employee.id, "name": employee.name, "status": "connected", "invite_code": None}
    unused = [invite for invite in employee.invites.all() if invite.used_at is None]
    code = unused[-1].code if unused else None
    return {"id": employee.id, "name": employee.name, "status": "invited", "invite_code": code}


def store_with_people(store: Store) -> dict:
    employees = sorted(
        store.employees.all(), key=lambda e: (e.status == EmployeeStatus.DISMISSED, e.name)
    )
    return {
        "id": store.id,
        "name": store.name,
        "address": store.address,
        "open_time": hhmm(store.open_time),
        "close_time": hhmm(store.close_time),
        "employees": [person(employee) for employee in employees],
    }


def template_item(template: TaskTemplate) -> dict:
    return {
        "id": template.id,
        "title": template.title,
        "kind": template.kind,
        "planned_time": hhmm(template.planned_time),
        "available_from": hhmm(template.available_from),
        "on_date": template.on_date.isoformat() if template.on_date else None,
        "tolerance_minutes": template.tolerance_minutes,
        "requires_photo": template.requires_photo,
        "requires_claim": template.requires_claim,
    }


def day_task(row: DayTaskRow, zone: ZoneInfo) -> dict:
    instance = row.instance
    completion = getattr(instance, "completion", None) if instance else None
    claim = getattr(instance, "claim", None) if instance else None
    return {
        "id": row.key,
        # Шаблон нужен карточке точки: задачу правят прямо из списка дня.
        "template_id": row.template.id,
        "title": row.template.title,
        "planned_time": hhmm(row.template.planned_time),
        "available_from": hhmm(row.template.available_from),
        "kind": row.template.kind,
        "status": row.status,
        "late_minutes": completion.late_minutes if completion else None,
        "done_by": completion.employee.name if completion else None,
        "done_at": hhmm(completion.completed_at.astimezone(zone)) if completion else None,
        "claimed_by": claim.employee.name if claim else None,
        "photo_url": f"/completions/{completion.id}/photo/" if completion and completion.photo else None,
    }


def week_dates(week_start: date) -> list[date]:
    return [week_start + timedelta(days=offset) for offset in range(7)]


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def gaps_of(store: Store, dates: list[date], shifts) -> list[dict]:
    """Uncovered parts of the working day for every date; `shifts` are (date, start, end) tuples."""
    result = []
    for day in dates:
        intervals = [(start, end) for shift_day, start, end in shifts if shift_day == day]
        for start, end in find_gaps(
            store.open_time, store.close_time, intervals, settings.SHIFT_BOUNDARY_TOLERANCE_MINUTES
        ):
            result.append({"date": day.isoformat(), "start": hhmm(start), "end": hhmm(end)})
    return result


def week_status(store: Store, week_start: date) -> str:
    statuses = list(
        Shift.objects.filter(store=store, date__in=week_dates(week_start)).values_list("status", flat=True)
    )
    published = bool(statuses) and all(status == ShiftStatus.PUBLISHED for status in statuses)
    return "published" if published else "draft"


def schedule_payload(store: Store, week_start: date) -> dict:
    dates = week_dates(week_start)
    shifts = list(
        Shift.objects.filter(store=store, date__in=dates).order_by("date", "start_time", "employee__name")
    )
    employees = store.employees.filter(status=EmployeeStatus.ACTIVE).order_by("name")
    return {
        "week_start": week_start.isoformat(),
        "status": week_status(store, week_start),
        "open_time": hhmm(store.open_time),
        "close_time": hhmm(store.close_time),
        "employees": [{"id": employee.id, "name": employee.name} for employee in employees],
        "shifts": [
            {
                "employee_id": shift.employee_id,
                "date": shift.date.isoformat(),
                "start": hhmm(shift.start_time),
                "end": hhmm(shift.end_time),
            }
            for shift in shifts
        ],
        "gaps": gaps_of(store, dates, [(s.date, s.start_time, s.end_time) for s in shifts]),
    }
