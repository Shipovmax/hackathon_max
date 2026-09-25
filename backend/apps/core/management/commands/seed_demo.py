import datetime as dt
import json
import struct
import zlib
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
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

DATA_FILE = Path(settings.BASE_DIR) / "testdata" / "demo_network.json"


def load_demo_data(path: Path = DATA_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_hhmm(value: str) -> dt.time:
    return dt.datetime.strptime(value, "%H:%M").time()


def demo_photo_png(width: int = 360, height: int = 480) -> bytes:
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


DEMO_LEAD_MINUTES = 30


def earlier(value: dt.time, minutes: int) -> dt.time:
    shifted = value.hour * 60 + value.minute - minutes
    return dt.time.min if shifted <= 0 else dt.time(shifted // 60, shifted % 60)


class Command(BaseCommand):
    help = "Create demo network, stores, employees, schedule and today's tasks from testdata/demo_network.json"

    def add_arguments(self, parser):
        parser.add_argument("--owner-max-id", type=int, help="MAX user id of the owner")
        parser.add_argument("--reset", action="store_true", help="delete existing demo stores first")

    @transaction.atomic
    def handle(self, *args, **options):
        data = load_demo_data()
        owner = self.resolve_owner(options.get("owner_max_id"))
        network, _ = Network.objects.get_or_create(owner=owner, defaults={"name": data["network"]})
        if network.name != data["network"]:
            network.name = data["network"]
            network.save(update_fields=["name"])

        if options["reset"]:
            self.reset(network)

        today = timezone.localdate()
        stores = {item["name"]: self.make_store(network, item, data["timezone"]) for item in data["stores"]}
        employees = self.make_employees(stores, data)
        self.make_templates(stores, data["task_templates"], today)
        shifts = self.make_shifts(stores, employees, data, today)
        busy = data["today"]
        self.make_today_tasks(stores[busy["store"]], employees[busy["performer"]], busy["tasks"], today)
        for name, store in stores.items():
            if name != busy["store"]:
                self.make_calm_day(store, today)

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

    def make_store(self, network: Network, item: dict, zone: str) -> Store:
        store, _ = Store.objects.get_or_create(
            network=network,
            name=item["name"],
            defaults={
                "address": item["address"],
                "open_time": parse_hhmm(item["open_time"]),
                "close_time": parse_hhmm(item["close_time"]),
                "timezone": zone,
            },
        )
        return store

    def make_employees(self, stores: dict[str, Store], data: dict) -> dict[str, Employee]:
        result: dict[str, Employee] = {}
        for person in data["staff"]:
            employee, created = Employee.objects.get_or_create(store=stores[person["store"]], name=person["name"])
            result[person["name"]] = employee
            if created:
                InviteCode.issue(employee)
        for person in data["dismissed"]:
            _, created = Employee.objects.get_or_create(
                store=stores[person["store"]], name=person["name"], defaults={"status": EmployeeStatus.DISMISSED}
            )
            if created:
                self.stdout.write(f"Добавлен уволенный сотрудник {person['name']} (история сохраняется)")
        return result

    def make_templates(self, stores: dict[str, Store], templates: list[dict], today: dt.date) -> None:
        for store in stores.values():
            for item in templates:
                planned = parse_hhmm(item["planned_time"])
                one_time = item["kind"] == TaskKind.ONE_TIME
                template, _ = TaskTemplate.objects.get_or_create(
                    store=store,
                    title=item["title"],
                    defaults={
                        "kind": item["kind"],
                        "planned_time": planned,
                        "available_from": earlier(planned, DEMO_LEAD_MINUTES),
                        "on_date": today if one_time else None,
                        "tolerance_minutes": item["tolerance_minutes"],
                        "requires_photo": item["requires_photo"],
                        "requires_claim": item["requires_claim"],
                        "photo_prompt": item["photo_prompt"],
                    },
                )
                if one_time and template.on_date != today:
                    template.on_date = today
                    template.save(update_fields=["on_date"])

    def make_shifts(self, stores: dict[str, Store], employees: dict[str, Employee], data: dict, today: dt.date) -> int:
        count = 0
        monday = today - dt.timedelta(days=today.weekday())
        current_week_only = {(item["name"], item["weekday"]): (item["start"], item["end"]) for item in data["current_week_only"]}
        Shift.objects.filter(
            store__in=stores.values(), date__gte=monday, date__lt=monday + dt.timedelta(days=14)
        ).delete()
        for person in data["staff"]:
            employee = employees[person["name"]]
            pattern = {int(day): hours for day, hours in person["shifts"].items()}
            for offset in range(14):
                date = monday + dt.timedelta(days=offset)
                current_week = offset < 7
                hours = pattern.get(date.weekday())
                if current_week:
                    hours = hours or current_week_only.get((person["name"], date.weekday()))
                if not hours:
                    continue
                start, end = hours
                _, created = Shift.objects.get_or_create(
                    employee=employee,
                    store=stores[person["store"]],
                    date=date,
                    defaults={
                        "start_time": parse_hhmm(start),
                        "end_time": parse_hhmm(end),
                        "status": ShiftStatus.PUBLISHED if current_week else ShiftStatus.DRAFT,
                    },
                )
                count += int(created)
        return count

    def make_calm_day(self, store: Store, today: dt.date) -> None:
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

    def make_today_tasks(self, store: Store, performer: Employee, states: dict, today: dt.date) -> None:
        tz = ZoneInfo(store.timezone)
        now = timezone.now().astimezone(tz)
        for template in TaskTemplate.objects.filter(store=store):
            state = states.get(template.title, {"status": TaskStatus.SCHEDULED})
            done_at = dt.datetime.combine(today, parse_hhmm(state["done_at"]), tzinfo=tz) if "done_at" in state else None
            if done_at is not None and done_at > now:
                done_at = None
                status = TaskStatus.SCHEDULED
            else:
                status = state["status"]
            instance, _ = TaskInstance.objects.get_or_create(
                template=template, date=today, defaults={"status": status}
            )
            if done_at is None:
                continue
            completion = getattr(instance, "completion", None)
            if completion is None:
                completion = Completion.objects.create(
                    instance=instance, employee=performer, completed_at=done_at, late_minutes=state["late_minutes"]
                )
            if not completion.photo:
                completion.photo.save("demo.png", ContentFile(demo_photo_png()))
