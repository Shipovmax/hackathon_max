"""Demo data for development and for the jury run. These are made-up stores and people, not real ones."""

import datetime as dt
from zoneinfo import ZoneInfo

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
        ("Света Р.", {0: (9, 16), 2: (9, 16), 4: (9, 16), 6: (9, 16)}),
        ("Кирилл Н.", {1: (16, 22), 3: (16, 22), 5: (16, 22)}),
    ],
}

TEMPLATES = [
    ("Открытие магазина", TaskKind.DAILY, dt.time(9, 0), 15, True, False, "Пришлите фото витрины и торгового зала"),
    ("Подготовка зала", TaskKind.DAILY, dt.time(10, 0), 30, True, False, "Пришлите фото торгового зала"),
    ("Приёмка поставки", TaskKind.ONE_TIME, dt.time(14, 0), 30, True, True, "Пришлите фото принятых коробок"),
    ("Закрытие смены", TaskKind.DAILY, dt.time(22, 0), 20, True, False, "Пришлите отчёт о закрытии смены"),
]


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
                TaskTemplate.objects.get_or_create(
                    store=store,
                    title=title,
                    defaults={
                        "kind": kind,
                        "planned_time": planned,
                        "on_date": today if kind == TaskKind.ONE_TIME else None,
                        "tolerance_minutes": tolerance,
                        "requires_photo": photo,
                        "requires_claim": claim,
                        "photo_prompt": prompt,
                    },
                )

    def make_shifts(self, stores: dict[str, Store], employees: dict[str, Employee], today: dt.date) -> int:
        count = 0
        for store_name, people in STAFF.items():
            store = stores[store_name]
            for person_name, pattern in people:
                employee = employees[person_name]
                for offset in range(14):
                    date = today + dt.timedelta(days=offset)
                    hours = pattern.get(date.weekday())
                    if not hours:
                        continue
                    start, end = hours
                    # This week is published so the bot can work; next week stays a draft for the schedule screen.
                    status = ShiftStatus.PUBLISHED if offset < 7 else ShiftStatus.DRAFT
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
            if done_at is None or hasattr(instance, "completion"):
                continue
            Completion.objects.create(
                instance=instance,
                employee=employees["Анна К."],
                completed_at=dt.datetime.combine(today, done_at, tzinfo=tz),
                late_minutes=late,
            )
