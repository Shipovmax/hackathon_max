from datetime import date, datetime, time, timedelta, timezone

from django.test import TestCase
from django.test.utils import override_settings

from apps.bot import texts
from apps.bot.scheduler import generate_task_instances, send_reminders
from apps.core.models import (
    Employee,
    EmployeeStatus,
    MaxAccount,
    Network,
    Shift,
    ShiftStatus,
    Store,
    TaskInstance,
    TaskKind,
    TaskStatus,
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


class RecordingClient:
    def __init__(self):
        self.sent = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)


@override_settings(REMINDER_MINUTES_BEFORE=5)
class SendRemindersTests(TestCase):
    def setUp(self):
        owner = MaxAccount.objects.create(max_user_id=1)
        network = Network.objects.create(owner=owner, name="Test network")
        self.store = Store.objects.create(
            network=network,
            name="Lenina, 14",
            open_time=time(9),
            close_time=time(22),
            timezone="Europe/Moscow",
        )
        self.employee_account = MaxAccount.objects.create(max_user_id=101)
        self.employee = Employee.objects.create(
            store=self.store,
            name="Anna",
            account=self.employee_account,
        )
        self.template = TaskTemplate.objects.create(
            store=self.store,
            title="Opening store",
            planned_time=time(12),
        )
        self.instance = TaskInstance.objects.create(
            template=self.template,
            date=date(2026, 9, 21),
        )
        self.shift = Shift.objects.create(
            employee=self.employee,
            store=self.store,
            date=self.instance.date,
            start_time=time(9),
            end_time=time(17),
            status=ShiftStatus.PUBLISHED,
        )
        self.client = RecordingClient()
        self.due_at = datetime(2026, 9, 21, 8, 55, tzinfo=timezone.utc)

    def test_sends_due_reminder_with_done_button_and_marks_instance(self):
        send_reminders(self.due_at, client=self.client)

        self.assertEqual(len(self.client.sent), 1)
        self.assertEqual(self.client.sent[0]["user_id"], self.employee_account.max_user_id)
        self.assertEqual(self.client.sent[0]["text"], texts.reminder(5, self.template.title))
        self.assertEqual(
            self.client.sent[0]["buttons"][0][0]["payload"], f"done:{self.instance.id}"
        )
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.reminder_sent_at, self.due_at)
        self.assertEqual(self.instance.status, TaskStatus.REMINDED)

    def test_does_not_send_the_same_reminder_twice(self):
        send_reminders(self.due_at, client=self.client)
        send_reminders(self.due_at, client=self.client)

        self.assertEqual(len(self.client.sent), 1)

    def test_sends_to_each_distinct_employee_whose_published_shift_covers_task(self):
        second_account = MaxAccount.objects.create(max_user_id=102)
        second_employee = Employee.objects.create(
            store=self.store,
            name="Igor",
            account=second_account,
        )
        Shift.objects.create(
            employee=second_employee,
            store=self.store,
            date=self.instance.date,
            start_time=time(12),
            end_time=time(20),
            status=ShiftStatus.PUBLISHED,
        )

        send_reminders(self.due_at, client=self.client)

        self.assertCountEqual(
            [call["user_id"] for call in self.client.sent],
            [self.employee_account.max_user_id, second_account.max_user_id],
        )

    def test_skips_draft_unbound_inactive_and_non_covering_employees(self):
        self.shift.status = ShiftStatus.DRAFT
        self.shift.save(update_fields=["status"])
        cases = [
            ("Unbound", None, EmployeeStatus.ACTIVE, time(9), time(17), ShiftStatus.PUBLISHED),
            ("Inactive", 102, EmployeeStatus.DISMISSED, time(9), time(17), ShiftStatus.PUBLISHED),
            ("Later", 103, EmployeeStatus.ACTIVE, time(13), time(20), ShiftStatus.PUBLISHED),
        ]
        for name, max_user_id, employee_status, start, end, shift_status in cases:
            account = MaxAccount.objects.create(max_user_id=max_user_id) if max_user_id else None
            employee = Employee.objects.create(
                store=self.store,
                name=name,
                account=account,
                status=employee_status,
            )
            Shift.objects.create(
                employee=employee,
                store=self.store,
                date=self.instance.date,
                start_time=start,
                end_time=end,
                status=shift_status,
            )

        send_reminders(self.due_at, client=self.client)

        self.assertEqual(self.client.sent, [])
        self.instance.refresh_from_db()
        self.assertIsNone(self.instance.reminder_sent_at)
        self.assertEqual(self.instance.status, TaskStatus.SCHEDULED)

    def test_only_sends_during_the_reminder_window(self):
        send_reminders(self.due_at - timedelta(seconds=1), client=self.client)
        send_reminders(self.due_at + timedelta(minutes=5), client=self.client)

        self.assertEqual(self.client.sent, [])
