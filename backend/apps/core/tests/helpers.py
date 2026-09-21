import datetime as dt

from apps.core.models import (
    Employee,
    MaxAccount,
    Network,
    Role,
    Shift,
    ShiftStatus,
    Store,
    TaskKind,
    TaskTemplate,
)

UTC = dt.timezone.utc


def moscow(hour: int, minute: int = 0, day: dt.date | None = None) -> dt.datetime:
    """An aware datetime for a Moscow wall-clock time (UTC+3, no DST)."""
    day = day or dt.date(2026, 9, 21)
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=dt.timezone(dt.timedelta(hours=3)))


def make_network(owner_id: int = 1001, name: str = "Test network") -> Network:
    owner, _ = MaxAccount.objects.get_or_create(
        max_user_id=owner_id, defaults={"first_name": "Owner", "role": Role.OWNER}
    )
    return Network.objects.create(owner=owner, name=name)


def make_store(network: Network, name: str = "Lenina, 14", open_at=(9, 0), close_at=(22, 0)) -> Store:
    return Store.objects.create(
        network=network, name=name, open_time=dt.time(*open_at), close_time=dt.time(*close_at)
    )


def make_template(
    store: Store,
    title: str = "Opening",
    at=(9, 0),
    tolerance: int = 15,
    *,
    claim: bool = False,
    one_time_on: dt.date | None = None,
) -> TaskTemplate:
    return TaskTemplate.objects.create(
        store=store,
        title=title,
        kind=TaskKind.ONE_TIME if one_time_on else TaskKind.DAILY,
        planned_time=dt.time(*at),
        on_date=one_time_on,
        tolerance_minutes=tolerance,
        requires_claim=claim,
    )


def make_shift(
    employee: Employee,
    start=(9, 0),
    end=(17, 0),
    day: dt.date | None = None,
    status: str = ShiftStatus.PUBLISHED,
) -> Shift:
    return Shift.objects.create(
        employee=employee,
        store=employee.store,
        date=day or dt.date(2026, 9, 21),
        start_time=dt.time(*start),
        end_time=dt.time(*end),
        status=status,
    )
