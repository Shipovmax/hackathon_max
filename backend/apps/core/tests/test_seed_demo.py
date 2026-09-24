import datetime as dt
import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.core.management.commands.seed_demo import load_demo_data
from apps.core.models import Employee, EmployeeStatus, Shift, ShiftStatus, Store, TaskInstance, TaskStatus, TaskTemplate

from .helpers import moscow

WEDNESDAY = dt.date(2026, 9, 23)


class DemoDataFileTests(TestCase):
    """testdata/demo_network.json — это тестовые данные для проверки, в них не должно быть висячих ссылок."""

    def test_every_reference_in_the_file_points_to_something_real(self):
        data = load_demo_data()
        stores = {item["name"] for item in data["stores"]}
        staff = {item["name"] for item in data["staff"]}
        titles = {item["title"] for item in data["task_templates"]}
        self.assertTrue({item["store"] for item in data["staff"] + data["dismissed"]} <= stores)
        self.assertTrue({item["name"] for item in data["current_week_only"]} <= staff)
        self.assertIn(data["today"]["store"], stores)
        self.assertIn(data["today"]["performer"], staff)
        self.assertTrue(set(data["today"]["tasks"]) <= titles)
        for person in data["staff"]:
            for day, (start, end) in person["shifts"].items():
                self.assertIn(int(day), range(7))
                self.assertLess(start, end, person["name"])


class SeedDemoTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def seed(self, hour=15, *args):
        with override_settings(MEDIA_ROOT=self.media), mock.patch(
            "django.utils.timezone.now", return_value=moscow(hour, 0, WEDNESDAY)
        ):
            call_command("seed_demo", "--owner-max-id", "4242", *args, stdout=StringIO())

    def test_builds_the_network_described_in_the_file(self):
        self.seed()
        data = load_demo_data()
        self.assertEqual(Store.objects.count(), len(data["stores"]))
        self.assertEqual(Employee.objects.filter(status=EmployeeStatus.ACTIVE).count(), len(data["staff"]))
        self.assertEqual(Employee.objects.filter(status=EmployeeStatus.DISMISSED).count(), len(data["dismissed"]))
        self.assertEqual(TaskTemplate.objects.count(), len(data["stores"]) * len(data["task_templates"]))
        # Текущая неделя опубликована, следующая — черновик.
        monday = WEDNESDAY - dt.timedelta(days=2)
        self.assertTrue(Shift.objects.filter(date__lt=monday + dt.timedelta(days=7), status=ShiftStatus.PUBLISHED).exists())
        self.assertFalse(Shift.objects.filter(date__gte=monday + dt.timedelta(days=7), status=ShiftStatus.PUBLISHED).exists())

    def test_today_at_the_busy_store_matches_the_mockup(self):
        self.seed(hour=15)
        statuses = dict(
            TaskInstance.objects.filter(template__store__name="Ленина, 14", date=WEDNESDAY).values_list(
                "template__title", "status"
            )
        )
        self.assertEqual(statuses["Открытие магазина"], TaskStatus.DONE_LATE)
        self.assertEqual(statuses["Подготовка зала"], TaskStatus.DONE_ON_TIME)

    def test_early_run_does_not_record_completions_from_the_future(self):
        self.seed(hour=8)
        opening = TaskInstance.objects.get(template__store__name="Ленина, 14", template__title="Открытие магазина")
        self.assertFalse(hasattr(opening, "completion"))
        self.assertEqual(opening.status, TaskStatus.SCHEDULED)

    def test_running_twice_does_not_duplicate_anything(self):
        self.seed()
        counts = (Store.objects.count(), Employee.objects.count(), Shift.objects.count(), TaskTemplate.objects.count())
        self.seed()
        self.assertEqual(
            counts, (Store.objects.count(), Employee.objects.count(), Shift.objects.count(), TaskTemplate.objects.count())
        )
