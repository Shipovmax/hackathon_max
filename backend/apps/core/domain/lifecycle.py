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
    template = instance.template
    return datetime.combine(instance.date, template.planned_time, tzinfo=store_zone(template.store))


def _related(instance: TaskInstance, name: str):
    return getattr(instance, name, None)


DONE_STATUSES = (TaskStatus.DONE_ON_TIME, TaskStatus.DONE_LATE)


def evaluate_status(instance: TaskInstance, now: datetime) -> str:
    template = instance.template
    completion = _related(instance, "completion")
    if completion is not None:
        if instance.status in DONE_STATUSES:
            return instance.status
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

    if instance.overdue_notified_at is not None:
        if not template.requires_claim:
            return TaskStatus.MISSED if past_day else TaskStatus.OVERDUE
        if _related(instance, "claim") is None:
            return TaskStatus.UNCLAIMED

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
        overdue_reported = instance.overdue_notified_at is not None and not template.requires_claim
        was_late = late > template.tolerance_minutes or overdue_reported
        instance.status = TaskStatus.DONE_LATE if was_late else TaskStatus.DONE_ON_TIME
        instance.awaiting_photo_employee = None
        instance.awaiting_photo_since = None
        instance.save(update_fields=["status", "awaiting_photo_employee", "awaiting_photo_since"])
    return completion


def templates_for(store: Store, day: date) -> list:
    closed = store.is_closed_on(day)
    return [
        template
        for template in store.task_templates.filter(is_active=True)
        if (template.kind == TaskKind.DAILY and not closed) or template.on_date == day
    ]


def ensure_instances(store: Store, day: date) -> list[TaskInstance]:
    templates = templates_for(store, day)
    for template in templates:
        TaskInstance.objects.get_or_create(template=template, date=day)
    return list(
        TaskInstance.objects.filter(template__in=templates, date=day)
        .select_related("template__store", "completion__employee", "claim__employee")
    )
