from datetime import time


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _time(minutes: int) -> time:
    minutes = max(0, min(minutes, 24 * 60 - 1))
    return time(minutes // 60, minutes % 60)


def find_gaps(
    day_open: time,
    day_close: time,
    shifts: list[tuple[time, time]],
    tolerance_minutes: int,
) -> list[tuple[time, time]]:
    """Uncovered parts of the working day. Gaps of at most `tolerance_minutes` at the edges or between shifts do not count."""
    open_at, close_at = _minutes(day_open), _minutes(day_close)

    merged: list[list[int]] = []
    for start, end in sorted((_minutes(start), _minutes(end)) for start, end in shifts):
        if merged and start <= merged[-1][1] + tolerance_minutes:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    gaps: list[tuple[int, int]] = []
    cursor = open_at
    for start, end in merged:
        if end <= cursor:
            continue
        if start > cursor + tolerance_minutes:
            gaps.append((cursor, min(start, close_at)))
        cursor = max(cursor, end)
        if cursor >= close_at:
            break
    if cursor < close_at - tolerance_minutes:
        gaps.append((cursor, close_at))

    return [(_time(start), _time(end)) for start, end in gaps]
