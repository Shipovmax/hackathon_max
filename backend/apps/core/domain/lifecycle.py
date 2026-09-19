from datetime import datetime


def planned_at(instance) -> datetime:
    """Planned moment of the task in the store's timezone (template.planned_time on instance.date)."""
    raise NotImplementedError


def evaluate_status(instance, now: datetime) -> str:
    """CLAUDE.md §5: status the task should have at `now` (on time / late / overdue / unclaimed / missed)."""
    raise NotImplementedError


def mark_done(instance, employee, now: datetime, photo: bytes | None = None):
    """Create the Completion and move the instance to done_on_time or done_late."""
    raise NotImplementedError
