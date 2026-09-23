"""Demo data for development and for the jury run. These are made-up stores and people, not real ones."""

import datetime as dt
import struct
import zlib
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    Claim,
    Completion,
    Employee,
    EmployeeStatus,
    InviteCode,
    MaxAccount,
    Network,
    Role,
    Shift,
    ShiftStatus,
    Store,
    TaskInstance,
    TaskKind,
    TaskStatus,
    TaskTemplate,
)

NETWORK_NAME = "Демо-сеть"
TZ = "Europe/Moscow"

STORES = [
    ("Ленина, 14", "ул. Ленина, 14"),
    ("Гагарина, 3", "ул. Гагарина, 3"),
    ("ТЦ «Восход»", "пр. Мира, 1, ТЦ «Восход»"),
]

# weekday (0 = Monday) -> shift hours; Thursday evening at the first store is left uncovered on purpose,
# so the coverage check has something to find.
STAFF = {
    "Ленина, 14": [
        ("Анна К.", {0: (9, 17), 1: (9, 17), 3: (9, 17), 4: (9, 17), 5: (9, 17)}),
        ("Игорь М.", {0: (14, 22), 1: (14, 22), 2: (14, 22), 4: (14, 22), 5: (14, 22), 6: (14, 22)}),
        ("Даша П.", {2: (9, 17), 6: (9, 17)}),
    ],
    "Гагарина, 3": [
        ("Олег В.", {0: (9, 16), 1: (9, 16), 2: (9, 16), 3: (9, 16), 4: (9, 16)}),
        ("Марина Л.", {0: (16, 22), 1: (16, 22), 2: (16, 22), 3: (16, 22), 4: (16, 22), 5: (9, 22), 6: (9, 22)}),
    ],
    "ТЦ «Восход»": [
        ("Света Р.", {0: (9, 16), 1: (9, 16), 2: (9, 16), 3: (9, 16), 4: (9, 16), 5: (9, 22), 6: (9, 22)}),
        ("Кирилл Н.", {0: (16, 22), 1: (16, 22), 2: (16, 22), 3: (16, 22), 4: (16, 22)}),
    ],
}

# Igor covers Thursday evening in the current (published) week only. Next week's draft therefore
# has exactly one uncovered window, the one the coverage check is meant to find.
CURRENT_WEEK_ONLY = {("Игорь М.", 3): (14, 22)}

TEMPLATES = [
    ("Открытие магазина", TaskKind.DAILY, dt.time(9, 0), 15, True, False, "Пришлите фото витрины и торгового зала"),
    ("Подготовка зала", TaskKind.DAILY, dt.time(10, 0), 30, True, False, "Пришлите фото торгового зала"),
    ("Приёмка поставки", TaskKind.ONE_TIME, dt.time(14, 0), 30, True, True, "Пришлите фото принятых коробок"),
    ("Закрытие смены", TaskKind.DAILY, dt.time(22, 0), 20, True, False, "Пришлите отчёт о закрытии смены"),
]


def demo_photo_png(width: int = 360, height: int = 480) -> bytes:
    """A plain placeholder picture, drawn without any imaging library: sky, wall and a shop-window band."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            if height * 0.55 < y < height * 0.85 and width * 0.1 < x < width * 0.9:
                rows += bytes((185, 195, 210))
            elif y < height * 0.4:
                rows += bytes((216 - y // 8, 222 - y // 8, 232))
            else:
                rows += bytes((200, 205, 214))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


# Демо-задачи можно отмечать за полчаса до планового времени, не раньше.
DEMO_LEAD_MINUTES = 30


def earlier(value: dt.time, minutes: int) -> dt.time:
    """Время минус минуты, без перехода через полночь."""
    shifted = value.hour * 60 + value.minute - minutes
    return dt.time.min if shifted <= 0 else dt.time(shifted // 60, shifted % 60)


class Command(BaseCommand):
    help = "Create demo network, stores, employees, schedule and today's tasks (test data)"

    def add_arguments(self, parser):
        parser.add_argument("--owner-max-id", type=int, help="MAX user id of the owner")
        parser.add_argument("--reset", action="store_true", help="delete existing demo stores first")

    @transaction.atomic
    def handle(self, *args, **options):
        owner = self.resolve_owner(options.get("owner_max_id"))
        network, _ = Network.objects.get_or_create(owner=owner, defaults={"name": NETWORK_NAME})
        if network.name != NETWORK_NAME:
            network.name = NETWORK_NAME
            network.save(update_fields=["name"])

        if options["reset"]:
            self.reset(network)

        today = timezone.localdate()
        stores = {name: self.make_store(network, name, address) for name, address in STORES}
        employees = self.make_employees(stores)
        self.make_templates(stores, today)
        shifts = self.make_shifts(stores, employees, today)
        self.make_today_tasks(stores["Ленина, 14"], employees, today)
        for name in ("Гагарина, 3", "ТЦ «Восход»"):
            self.make_calm_day(stores[name], today)

        self.stdout.write(self.style.SUCCESS(f"Сеть «{network.name}» владельца {owner.max_user_id} готова"))
        self.stdout.write(f"Точек: {len(stores)}, сотрудников: {len(employees)}, смен: {shifts}")
        self.stdout.write("\nКоды приглашения (отправить боту, чтобы привязать сотрудника):")
        for employee in Employee.objects.filter(store__network=network, account__isnull=True).order_by("store", "name"):
            code = employee.invites.filter(used_at__isnull=True).first()
            if code:
                self.stdout.write(f"  {employee.store.name:<16} {employee.name:<12} {code.code}")

    def resolve_owner(self, max_user_id: int | None) -> MaxAccount:
        if max_user_id:
            owner, _ = MaxAccount.objects.get_or_create(max_user_id=max_user_id)
            if owner.role != Role.OWNER:
                owner.role = Role.OWNER
                owner.save(update_fields=["role"])
            return owner
        owner = MaxAccount.objects.filter(role=Role.OWNER).order_by("id").first()
        if owner is None:
            raise CommandError(
                "Владелец не найден. Откройте бота в MAX, нажмите «Я владелец», "
                "либо передайте --owner-max-id <ваш MAX id>."
            )
        return owner

    def reset(self, network: Network) -> None:
        stores = Store.objects.filter(network=network)
        instances = TaskInstance.objects.filter(template__store__in=stores)
        Completion.objects.filter(instance__in=instances).delete()
        Claim.objects.filter(instance__in=instances).delete()
        instances.delete()
        TaskTemplate.objects.filter(store__in=stores).delete()
        Shift.objects.filter(store__in=stores).delete()
        employees = Employee.objects.filter(store__in=stores)
        InviteCode.objects.filter(employee__in=employees).delete()
        employees.delete()
        stores.delete()
        self.stdout.write("Прежние демо-данные удалены")

    def make_store(self, network: Network, name: str, address: str) -> Store:
        store, _ = Store.objects.get_or_create(
            network=network,
            name=name,
            defaults={
                "address": address,
                "open_time": dt.time(9, 0),
                "close_time": dt.time(22, 0),
                "timezone": TZ,
            },
        )
        return store

    def make_employees(self, stores: dict[str, Store]) -> dict[str, Employee]:
        result: dict[str, Employee] = {}
        for store_name, people in STAFF.items():
            for person_name, _ in people:
                employee, created = Employee.objects.get_or_create(
                    store=stores[store_name], name=person_name
                )
                result[person_name] = employee
                if created:
                    InviteCode.issue(employee)
        dismissed, created = Employee.objects.get_or_create(
            store=stores["Ленина, 14"], name="Пётр С.", defaults={"status": EmployeeStatus.DISMISSED}
        )
        if created:
            self.stdout.write("Добавлен уволенный сотрудник Пётр С. (история сохраняется)")
        return result

    def make_templates(self, stores: dict[str, Store], today: dt.date) -> None:
        for store in stores.values():
            for title, kind, planned, tolerance, photo, claim, prompt in TEMPLATES:
                template, _ = TaskTemplate.objects.get_or_create(
                    store=store,
                    title=title,
                    defaults={
                        "kind": kind,
                        "planned_time": planned,
                        "available_from": earlier(planned, DEMO_LEAD_MINUTES),
                        "on_date": today if kind == TaskKind.ONE_TIME else None,
                        "tolerance_minutes": tolerance,
                        "requires_photo": photo,
                        "requires_claim": claim,
                        "photo_prompt": prompt,
                    },
                )
                # The one-off delivery always happens "today", so the demo scenario is visible on any day.
                if kind == TaskKind.ONE_TIME and template.on_date != today:
                    template.on_date = today
                    template.save(update_fields=["on_date"])

    def make_shifts(self, stores: dict[str, Store], employees: dict[str, Employee], today: dt.date) -> int:
        """Two whole weeks: the current one published so the bot can work, the next one a draft."""
        count = 0
        monday = today - dt.timedelta(days=today.weekday())
        # The demo schedule is always restored to its intended shape, so re-running the command repairs it.
        Shift.objects.filter(
            store__in=stores.values(), date__gte=monday, date__lt=monday + dt.timedelta(days=14)
        ).delete()
        for store_name, people in STAFF.items():
            store = stores[store_name]
            for person_name, pattern in people:
                employee = employees[person_name]
                for offset in range(14):
                    date = monday + dt.timedelta(days=offset)
                    current_week = offset < 7
                    hours = pattern.get(date.weekday())
                    if current_week:
                        hours = hours or CURRENT_WEEK_ONLY.get((person_name, date.weekday()))
                    if not hours:
                        continue
                    start, end = hours
                    status = ShiftStatus.PUBLISHED if current_week else ShiftStatus.DRAFT
                    _, created = Shift.objects.get_or_create(
                        employee=employee,
                        store=store,
                        date=date,
                        defaults={
                            "start_time": dt.time(start, 0),
                            "end_time": dt.time(end, 0),
                            "status": status,
                        },
                    )
                    count += int(created)
        return count

    def make_calm_day(self, store: Store, today: dt.date) -> None:
        """A store without remarks: every task that is already due was done on time."""
        tz = ZoneInfo(store.timezone)
        now = timezone.now().astimezone(tz)
        performer = Employee.objects.filter(store=store, status=EmployeeStatus.ACTIVE).order_by("name").first()
        for template in TaskTemplate.objects.filter(store=store, kind=TaskKind.DAILY):
            instance, _ = TaskInstance.objects.get_or_create(template=template, date=today)
            done_at = dt.datetime.combine(today, template.planned_time, tzinfo=tz) + dt.timedelta(minutes=2)
            if done_at > now or performer is None or hasattr(instance, "completion"):
                continue
            completion = Completion.objects.create(
                instance=instance, employee=performer, completed_at=done_at, late_minutes=2
            )
            completion.photo.save("demo.png", ContentFile(demo_photo_png()))
            instance.status = TaskStatus.DONE_ON_TIME
            instance.save(update_fields=["status"])

    def make_today_tasks(self, store: Store, employees: dict[str, Employee], today: dt.date) -> None:
        """Today at the first store looks like the mock-up: opening late, hall on time, delivery nobody took."""
        tz = ZoneInfo(store.timezone)
        states = {
            "Открытие магазина": (TaskStatus.DONE_LATE, dt.time(9, 40), 40),
            "Подготовка зала": (TaskStatus.DONE_ON_TIME, dt.time(9, 55), 0),
            "Приёмка поставки": (TaskStatus.UNCLAIMED, None, None),
            "Закрытие смены": (TaskStatus.SCHEDULED, None, None),
        }
        for template in TaskTemplate.objects.filter(store=store):
            status, done_at, late = states.get(template.title, (TaskStatus.SCHEDULED, None, None))
            instance, _ = TaskInstance.objects.get_or_create(
                template=template, date=today, defaults={"status": status}
            )
            if done_at is None:
                continue
            completion = getattr(instance, "completion", None)
            if completion is None:
                completion = Completion.objects.create(
                    instance=instance,
                    employee=employees["Анна К."],
                    completed_at=dt.datetime.combine(today, done_at, tzinfo=tz),
                    late_minutes=late,
                )
            if not completion.photo:
                completion.photo.save("demo.png", ContentFile(demo_photo_png()))
