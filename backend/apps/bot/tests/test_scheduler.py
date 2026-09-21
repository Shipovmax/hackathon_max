from datetime import date, datetime, time, timedelta, timezone

from django.test import TestCase
from django.test.utils import override_settings

from apps.bot import texts
from apps.bot.scheduler import (
    expire_photo_waits,
    generate_task_instances,
    mark_overdue,
    send_reminders,
    send_shift_start_messages,
)
from apps.core.domain.lifecycle import mark_done
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
        self.error = None

    def send_message(self, **kwargs):
        if self.error:
            raise self.error
        self.sent.append(kwargs)


class SendShiftStartMessagesTests(TestCase):
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
        self.shift = Shift.objects.create(
            employee=self.employee,
            store=self.store,
            date=date(2026, 9, 21),
            start_time=time(9),
            end_time=time(17),
            status=ShiftStatus.PUBLISHED,
        )
        self.client = RecordingClient()
        self.starts_at = datetime(2026, 9, 21, 6, tzinfo=timezone.utc)

    def template(self, title, planned_time, **kwargs):
        return TaskTemplate.objects.create(
            store=self.store,
            title=title,
            planned_time=planned_time,
            **kwargs,
        )

    def test_sends_sorted_tasks_and_marks_shift_as_notified(self):
        self.template("Prepare sales floor", time(10))
        self.template("Open store", time(9))
        self.template(
            "Delivery",
            time(14),
            kind=TaskKind.ONE_TIME,
            on_date=self.shift.date,
        )

        send_shift_start_messages(self.starts_at, client=self.client)

        self.assertEqual(
            self.client.sent,
            [
                {
                    "user_id": self.employee_account.max_user_id,
                    "text": (
                        "Смена началась. Lenina, 14 · до 17:00\n\n"
                        "09:00 Open store\n"
                        "10:00 Prepare sales floor\n"
                        "14:00 Delivery"
                    ),
                }
            ],
        )
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.start_notified_at, self.starts_at)

    def test_does_not_send_shift_start_twice(self):
        send_shift_start_messages(self.starts_at, client=self.client)
        send_shift_start_messages(self.starts_at + timedelta(seconds=30), client=self.client)

        self.assertEqual(len(self.client.sent), 1)

    def test_uses_first_tick_during_shift_but_not_before_or_after_it(self):
        send_shift_start_messages(self.starts_at - timedelta(seconds=1), client=self.client)
        self.assertEqual(self.client.sent, [])

        delayed_tick = self.starts_at + timedelta(minutes=20)
        send_shift_start_messages(delayed_tick, client=self.client)
        self.assertEqual(len(self.client.sent), 1)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.start_notified_at, delayed_tick)

        self.shift.start_notified_at = None
        self.shift.save(update_fields=["start_notified_at"])
        send_shift_start_messages(
            datetime(2026, 9, 21, 14, tzinfo=timezone.utc),
            client=self.client,
        )
        self.assertEqual(len(self.client.sent), 1)

    def test_ignores_inactive_and_non_matching_task_templates(self):
        self.template("Active daily", time(9))
        self.template("Inactive", time(10), is_active=False)
        self.template(
            "Other date",
            time(11),
            kind=TaskKind.ONE_TIME,
            on_date=date(2026, 9, 22),
        )

        send_shift_start_messages(self.starts_at, client=self.client)

        self.assertIn("09:00 Active daily", self.client.sent[0]["text"])
        self.assertNotIn("Inactive", self.client.sent[0]["text"])
        self.assertNotIn("Other date", self.client.sent[0]["text"])

    def test_sends_header_without_blank_task_section_when_store_has_no_tasks(self):
        send_shift_start_messages(self.starts_at, client=self.client)

        self.assertEqual(
            self.client.sent[0]["text"],
            "Смена началась. Lenina, 14 · до 17:00",
        )

    def test_skips_draft_unbound_and_inactive_employees(self):
        cases = [
            (ShiftStatus.DRAFT, self.employee_account, EmployeeStatus.ACTIVE),
            (ShiftStatus.PUBLISHED, None, EmployeeStatus.ACTIVE),
            (ShiftStatus.PUBLISHED, self.employee_account, EmployeeStatus.DISMISSED),
        ]
        for shift_status, account, employee_status in cases:
            with self.subTest(
                shift_status=shift_status,
                has_account=account is not None,
                employee_status=employee_status,
            ):
                self.shift.status = shift_status
                self.shift.start_notified_at = None
                self.shift.save(update_fields=["status", "start_notified_at"])
                self.employee.account = account
                self.employee.status = employee_status
                self.employee.save(update_fields=["account", "status"])
                self.client.sent.clear()

                send_shift_start_messages(self.starts_at, client=self.client)

                self.assertEqual(self.client.sent, [])
                self.shift.refresh_from_db()
                self.assertIsNone(self.shift.start_notified_at)


@override_settings(PHOTO_WAIT_MINUTES=10)
class ExpirePhotoWaitsTests(TestCase):
    def setUp(self):
        owner = MaxAccount.objects.create(max_user_id=1)
        network = Network.objects.create(owner=owner, name="Test network")
        store = Store.objects.create(
            network=network,
            name="Lenina, 14",
            open_time=time(9),
            close_time=time(22),
        )
        employee = Employee.objects.create(store=store, name="Anna")
        template = TaskTemplate.objects.create(
            store=store,
            title="Opening store",
            planned_time=time(9),
        )
        self.requested_at = datetime(2026, 9, 21, 6, tzinfo=timezone.utc)
        self.instance = TaskInstance.objects.create(
            template=template,
            date=date(2026, 9, 21),
            status=TaskStatus.AWAITING_PHOTO,
            reminder_sent_at=self.requested_at - timedelta(minutes=5),
            awaiting_photo_employee=employee,
            awaiting_photo_since=self.requested_at,
        )

    def test_restores_reminded_status_and_clears_photo_reservation_at_timeout(self):
        expire_photo_waits(self.requested_at + timedelta(minutes=10))

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.REMINDED)
        self.assertIsNone(self.instance.awaiting_photo_employee)
        self.assertIsNone(self.instance.awaiting_photo_since)

    def test_restores_scheduled_status_when_there_was_no_reminder(self):
        self.instance.reminder_sent_at = None
        self.instance.save(update_fields=["reminder_sent_at"])

        expire_photo_waits(self.requested_at + timedelta(minutes=10))

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.SCHEDULED)

    def test_does_not_expire_before_timeout_and_repeated_calls_are_safe(self):
        expire_photo_waits(self.requested_at + timedelta(minutes=10, seconds=-1))
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.AWAITING_PHOTO)

        expire_photo_waits(self.requested_at + timedelta(minutes=10))
        expire_photo_waits(self.requested_at + timedelta(minutes=11))
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.REMINDED)


class MarkOverdueTests(TestCase):
    def setUp(self):
        self.owner = MaxAccount.objects.create(max_user_id=1)
        network = Network.objects.create(owner=self.owner, name="Test network")
        self.store = Store.objects.create(
            network=network,
            name="Lenina, 14",
            open_time=time(9),
            close_time=time(22),
            timezone="Europe/Moscow",
        )
        self.template = TaskTemplate.objects.create(
            store=self.store,
            title="Open store",
            planned_time=time(9),
            tolerance_minutes=15,
            requires_photo=False,
        )
        self.instance = TaskInstance.objects.create(
            template=self.template,
            date=date(2026, 9, 21),
        )
        self.deadline = datetime(2026, 9, 21, 6, 15, tzinfo=timezone.utc)
        self.client = RecordingClient()

    def test_marks_overdue_notifies_owner_and_adds_store_deep_link_once(self):
        now = self.deadline + timedelta(seconds=1)

        mark_overdue(now, client=self.client)
        mark_overdue(now + timedelta(seconds=30), client=self.client)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.OVERDUE)
        self.assertEqual(self.instance.overdue_notified_at, now)
        self.assertEqual(len(self.client.sent), 1)
        notification = self.client.sent[0]
        self.assertEqual(notification["user_id"], self.owner.max_user_id)
        self.assertEqual(
            notification["text"],
            "Lenina, 14: задача «Open store» не отмечена. Плановое время — 09:00.",
        )
        self.assertTrue(
            notification["buttons"][0][0]["url"].endswith(
                f"?startapp=store_{self.store.id}_20260921"
            )
        )

    def test_uses_strict_tolerance_boundary(self):
        mark_overdue(self.deadline, client=self.client)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.SCHEDULED)
        self.assertEqual(self.client.sent, [])

        mark_overdue(self.deadline + timedelta(seconds=1), client=self.client)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.OVERDUE)
        self.assertEqual(len(self.client.sent), 1)

    def test_completed_and_claim_tasks_are_not_reported_as_overdue(self):
        employee = Employee.objects.create(store=self.store, name="Anna")
        mark_done(self.instance, employee, self.deadline - timedelta(minutes=10))
        claim_template = TaskTemplate.objects.create(
            store=self.store,
            title="Delivery",
            planned_time=time(9),
            requires_photo=False,
            requires_claim=True,
        )
        claim_instance = TaskInstance.objects.create(
            template=claim_template,
            date=self.instance.date,
        )

        mark_overdue(self.deadline + timedelta(seconds=1), client=self.client)

        self.instance.refresh_from_db()
        claim_instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.DONE_ON_TIME)
        self.assertEqual(claim_instance.status, TaskStatus.SCHEDULED)
        self.assertEqual(self.client.sent, [])

    def test_past_day_becomes_missed_without_sending_a_late_overdue_alert(self):
        mark_overdue(
            datetime(2026, 9, 22, 9, tzinfo=timezone.utc),
            client=self.client,
        )

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.SCHEDULED)
        self.assertIsNone(self.instance.overdue_notified_at)
        self.assertEqual(self.client.sent, [])

    def test_failed_notification_leaves_task_available_for_retry(self):
        self.client.error = RuntimeError("MAX unavailable")

        with self.assertRaisesRegex(RuntimeError, "MAX unavailable"):
            mark_overdue(self.deadline + timedelta(seconds=1), client=self.client)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.SCHEDULED)
        self.assertIsNone(self.instance.overdue_notified_at)


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
