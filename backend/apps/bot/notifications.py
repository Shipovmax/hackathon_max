def notify_owner_overdue(instance) -> None:
    """Once per task when the tolerance expires without a completion (CLAUDE.md §5)."""
    raise NotImplementedError


def notify_owner_closed_late(instance) -> None:
    """Closing notification, sent once when an overdue task is finally completed."""
    raise NotImplementedError


def notify_owner_unclaimed(instance) -> None:
    """«Задачу никто не взял»: a claim task nobody took by its planned time."""
    raise NotImplementedError
