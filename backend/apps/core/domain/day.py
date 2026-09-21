from dataclasses import dataclass
from datetime import date, datetime

from apps.core.models import (
    Shift,
    ShiftStatus,
    Store,
    TaskInstance,
    TaskKind,
    TaskStatus,
    TaskTemplate,
)

from .lifecycle import ensure_instances, evaluate_status, store_today


@dataclass
class DayTaskRow:
    key: int
    template: TaskTemplate
    instance: TaskInstance | None
    status: str


def day_tasks(store: Store, day: date, now: datetime) -> list[DayTaskRow]:
    """Tasks of one store for one day, in chronological order.

    Today the rows are created on demand, future days are shown from the templates without saving,
    past days show only what was actually recorded.
    """
    today = store_today(store, now)

    if day == today:
        instances = ensure_instances(store, day)
    elif day > today:
        templates = [
            template
            for template in store.task_templates.filter(is_active=True)
            if template.kind == TaskKind.DAILY or template.on_date == day
        ]
        rows = [DayTaskRow(t.id, t, None, TaskStatus.SCHEDULED) for t in templates]
        return sorted(rows, key=lambda row: row.template.planned_time)
    else:
        instances = list(
            TaskInstance.objects.filter(template__store=store, date=day).select_related(
                "template__store", "completion__employee", "claim__employee"
            )
        )

    rows = [DayTaskRow(i.id, i.template, i, evaluate_status(i, now)) for i in instances]
    return sorted(rows, key=lambda row: row.template.planned_time)


def published_shifts(store: Store, day: date):
    return (
        Shift.objects.filter(store=store, date=day, status=ShiftStatus.PUBLISHED)
        .select_related("employee")
        .order_by("start_time", "employee__name")
    )
