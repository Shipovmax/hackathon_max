from datetime import time


def find_gaps(
    day_open: time,
    day_close: time,
    shifts: list[tuple[time, time]],
    tolerance_minutes: int,
) -> list[tuple[time, time]]:
    """CLAUDE.md §7: merge shift intervals and return the parts of open..close nobody covers; gaps within the tolerance at the edges do not count."""
    raise NotImplementedError
