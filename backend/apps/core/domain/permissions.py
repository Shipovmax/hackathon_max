from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum

from django.conf import settings

from apps.core.models import EmployeeStatus, Shift, ShiftStatus

from .lifecycle import store_today, store_zone


class MarkDenial(str, Enum):
    DAY_OFF = "day_off"
    NOT_STARTED = "not_started"
    ENDED = "ended"
    ALREADY_DONE = "already_done"


@dataclass(frozen=True)
class MarkDecision:
    allowed: bool
    denial: MarkDenial | None = None
    shift_start: time | None = None
    shift_end: time | None = None
    done_by: str | None = None
    done_at: time | None = None


def check_can_mark(employee, instance, now: datetime) -> MarkDecision:
    """Allowed only while the employee's published shift at this store is running (± boundary tolerance).

    A denial carries what the message needs: the employee's shift hours, or who already did the task.
    """
    completion = getattr(instance, "completion", None)
    if completion is not None:
        zone = store_zone(instance.template.store)
        return MarkDecision(
            False,
            MarkDenial.ALREADY_DONE,
            done_by=completion.employee.name,
            done_at=completion.completed_at.astimezone(zone).time().replace(second=0, microsecond=0),
        )

    store = instance.template.store
    if employee.status != EmployeeStatus.ACTIVE or employee.store_id != store.id:
        return MarkDecision(False, MarkDenial.DAY_OFF)

    if instance.date != store_today(store, now):
        return MarkDecision(False, MarkDenial.ENDED)

    shifts = list(
        Shift.objects.filter(
            employee=employee, store=store, date=instance.date, status=ShiftStatus.PUBLISHED
        ).order_by("start_time")
    )
    if not shifts:
        return MarkDecision(False, MarkDenial.DAY_OFF)

    zone = store_zone(store)
    tolerance = timedelta(minutes=settings.SHIFT_BOUNDARY_TOLERANCE_MINUTES)

    def bounds(shift):
        start = datetime.combine(shift.date, shift.start_time, tzinfo=zone)
        end = datetime.combine(shift.date, shift.end_time, tzinfo=zone)
        return start - tolerance, end + tolerance

    for shift in shifts:
        start, end = bounds(shift)
        if start <= now <= end:
            return MarkDecision(True, shift_start=shift.start_time, shift_end=shift.end_time)

    upcoming = [shift for shift in shifts if now < bounds(shift)[0]]
    if upcoming:
        return MarkDecision(
            False, MarkDenial.NOT_STARTED, shift_start=upcoming[0].start_time, shift_end=upcoming[0].end_time
        )
    return MarkDecision(False, MarkDenial.ENDED, shift_start=shifts[-1].start_time, shift_end=shifts[-1].end_time)
