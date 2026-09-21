from datetime import date, datetime, time, timezone

from django.test import TestCase

from apps.bot.scheduler import generate_task_instances
from apps.core.models import (
    MaxAccount,
    Network,
    Store,
    TaskInstance,
    TaskKind,
    TaskTemplate,
)


class GenerateTaskInstancesTests(TestCase):
    def setUp(self):
        owner = MaxAccount.objects.create(max_user_id=1)
        network = Network.objects.create(owner=owner, name="Test network")
        self.moscow = Store.objects.create(
            network=network,
            name="Moscow",
            open_time=time(9),
            close_time=time(22),
            timezone="Europe/Moscow",
        )
        self.honolulu = Store.objects.create(
            network=network,
            name="Honolulu",
            open_time=time(9),
            close_time=time(22),
            timezone="Pacific/Honolulu",
        )
        self.inactive_store = Store.objects.create(
            network=network,
            name="Closed",
            open_time=time(9),
            close_time=time(22),
            timezone="Europe/Moscow",
            is_active=False,
        )

    def template(self, store, title, *, kind=TaskKind.DAILY, on_date=None, is_active=True):
        return TaskTemplate.objects.create(
            store=store,
            title=title,
            kind=kind,
            on_date=on_date,
            planned_time=time(12),
            is_active=is_active,
        )

    def test_creates_daily_and_matching_one_time_tasks_for_each_stores_local_date(self):
        now = datetime(2026, 9, 20, 22, 30, tzinfo=timezone.utc)
        moscow_daily = self.template(self.moscow, "Moscow daily")
        moscow_one_time = self.template(
            self.moscow,
            "Moscow one-time",
            kind=TaskKind.ONE_TIME,
            on_date=date(2026, 9, 21),
        )
        honolulu_daily = self.template(self.honolulu, "Honolulu daily")
        honolulu_one_time = self.template(
            self.honolulu,
            "Honolulu one-time",
            kind=TaskKind.ONE_TIME,
            on_date=date(2026, 9, 20),
        )

        generate_task_instances(now)

        self.assertTrue(
            TaskInstance.objects.filter(template=moscow_daily, date=date(2026, 9, 21)).exists()
        )
        self.assertTrue(
            TaskInstance.objects.filter(template=moscow_one_time, date=date(2026, 9, 21)).exists()
        )
        self.assertTrue(
            TaskInstance.objects.filter(template=honolulu_daily, date=date(2026, 9, 20)).exists()
        )
        self.assertTrue(
            TaskInstance.objects.filter(
                template=honolulu_one_time, date=date(2026, 9, 20)
            ).exists()
        )

    def test_skips_inactive_templates_non_matching_dates_and_inactive_stores(self):
        now = datetime(2026, 9, 21, 9, tzinfo=timezone.utc)
        inactive_template = self.template(self.moscow, "Inactive", is_active=False)
        other_date = self.template(
            self.moscow,
            "Other date",
            kind=TaskKind.ONE_TIME,
            on_date=date(2026, 9, 22),
        )
        closed_store_template = self.template(self.inactive_store, "Closed store task")

        generate_task_instances(now)

        self.assertFalse(
            TaskInstance.objects.filter(
                template__in=[inactive_template, other_date, closed_store_template]
            ).exists()
        )

    def test_is_idempotent_when_scheduler_runs_repeatedly(self):
        now = datetime(2026, 9, 21, 9, tzinfo=timezone.utc)
        template = self.template(self.moscow, "Daily")

        generate_task_instances(now)
        generate_task_instances(now)

        self.assertEqual(TaskInstance.objects.filter(template=template).count(), 1)
