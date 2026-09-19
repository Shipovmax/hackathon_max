from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MarkDenial(str, Enum):
    DAY_OFF = "day_off"
    NOT_STARTED = "not_started"
    ENDED = "ended"
    ALREADY_DONE = "already_done"


@dataclass(frozen=True)
class MarkDecision:
    allowed: bool
    denial: MarkDenial | None = None


def check_can_mark(employee, instance, now: datetime) -> MarkDecision:
    """CLAUDE.md §4: allowed only while the employee's published shift at this store is active, with boundary tolerance."""
    raise NotImplementedError
