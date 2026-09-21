from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.core.models import Completion, Store, TaskInstance, TaskKind, TaskStatus


def store_zone(store: Store) -> ZoneInfo:
    return ZoneInfo(store.timezone)


def store_today(store: Store, now: datetime | None = None) -> date:
    return (now or timezone.now()).astimezone(store_zone(store)).date()


def planned_at(instance: TaskInstance) -> datetime:
    """Planned moment of the task in the store's timezone."""
    template = instance.template
    return datetime.combine(instance.date, template.planned_time, tzinfo=store_zone(template.store))


def _related(instance: TaskInstance, name: str):
    return getattr(instance, name, None)


def evaluate_status(instance: TaskInstance, now: datetime) -> str:
    """Status the task has at `now`, derived from what was actually recorded (CLAUDE.md, section 5)."""
    template = instance.template
    completion = _related(instance, "completion")
    if completion is not None:
        late = completion.late_minutes > template.tolerance_minutes
        return TaskStatus.DONE_LATE if late else TaskStatus.DONE_ON_TIME

    planned = planned_at(instance)
    deadline = planned + timedelta(minutes=template.tolerance_minutes)
    past_day = instance.date < store_today(template.store, now)

    if (
        instance.status == TaskStatus.AWAITING_PHOTO
        and instance.awaiting_photo_since is not None
        and now - instance.awaiting_photo_since <= timedelta(minutes=settings.PHOTO_WAIT_MINUTES)
    ):
        return TaskStatus.AWAITING_PHOTO

    if template.requires_claim and _related(instance, "claim") is None:
        if now >= planned:
            return TaskStatus.UNCLAIMED
    elif now > deadline:
        return TaskStatus.MISSED if past_day else TaskStatus.OVERDUE

    return TaskStatus.REMINDED if instance.reminder_sent_at else TaskStatus.SCHEDULED


def mark_done(
    instance: TaskInstance,
    employee,
    now: datetime,
    photo: bytes | None = None,
    photo_token: str = "",
) -> Completion:
    """Record the completion. Lateness is measured from the planned time, status from the task's tolerance."""
    existing = _related(instance, "completion")
    if existing is not None:
        return existing

    template = instance.template
    late = max(0, int((now - planned_at(instance)).total_seconds() // 60))
    with transaction.atomic():
        completion = Completion(
            instance=instance,
            employee=employee,
            completed_at=now,
            late_minutes=late,
            photo_token=photo_token,
        )
        if photo:
            completion.photo.save(f"task-{instance.id}.jpg", ContentFile(photo), save=False)
        completion.save()
        instance.status = (
            TaskStatus.DONE_LATE if late > template.tolerance_minutes else TaskStatus.DONE_ON_TIME
        )
        instance.awaiting_photo_employee = None
        instance.awaiting_photo_since = None
        instance.save(update_fields=["status", "awaiting_photo_employee", "awaiting_photo_since"])
    return completion


def ensure_instances(store: Store, day: date) -> list[TaskInstance]:
    """Create the day's TaskInstance rows from active templates. Safe to call repeatedly."""
    templates = [
        template
        for template in store.task_templates.filter(is_active=True)
        if template.kind == TaskKind.DAILY or template.on_date == day
    ]
    for template in templates:
        TaskInstance.objects.get_or_create(template=template, date=day)
    return list(
        TaskInstance.objects.filter(template__in=templates, date=day)
        .select_related("template__store", "completion__employee", "claim__employee")
    )
