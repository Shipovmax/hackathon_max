from datetime import date, datetime, time, timedelta, timezone

from django.test import TestCase
from django.test.utils import override_settings

from apps.bot import texts
from apps.bot.scheduler import (
    escalate_unclaimed,
    expire_photo_waits,
    generate_task_instances,
    mark_overdue,
    refresh_changed_boards,
    send_claim_requests,
    send_closing_notifications,
    send_reminders,
    send_shift_start_messages,
    send_shift_summaries,
)
from apps.core.domain.lifecycle import mark_done
from apps.core.models import (
    Claim,
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

        self.assertEqual(len(self.client.sent), 1)
        message = self.client.sent[0]
        self.assertEqual(message["user_id"], self.employee_account.max_user_id)
        self.assertEqual(
            message["text"],
            "Смена началась\n"
            "Lenina, 14 · смена 09:00–17:00\n"
            "Выполнено 0 из 3 задач\n\n"
            "○ 09:00 Open store — отметить до 09:15, нужно фото\n"
            "○ 10:00 Prepare sales floor — отметить до 10:15, нужно фото\n"
            "○ 14:00 Delivery — отметить до 14:15, нужно фото\n\n"
            "Отметьте задачу кнопкой под сообщением.",
        )
        # Кнопка на каждую задачу, подпись называет её целиком.
        self.assertEqual(
            [row[0]["text"] for row in message["buttons"]],
            [
                "Выполнено · 09:00 Open store",
                "Выполнено · 10:00 Prepare sales floor",
                "Выполнено · 14:00 Delivery",
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
            "Смена началась\nLenina, 14 · смена 09:00–17:00\nЗадач на эту смену нет",
        )
        self.assertEqual(self.client.sent[0]["buttons"], [])

    def test_shift_start_records_when_the_board_was_shown(self):
        send_shift_start_messages(self.starts_at, client=self.client)

        self.shift.refresh_from_db()
        self.assertEqual(self.shift.board_sent_at, self.starts_at)

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


class RefreshChangedBoardsTests(TestCase):
    """Владелец правит задачи точки среди дня — смена получает обновлённый список."""

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
            store=self.store, name="Anna", account=self.employee_account
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
        # 12:00 по Москве: смена идёт, список сотрудник видел минуту назад.
        self.now = datetime(2026, 9, 21, 9, tzinfo=timezone.utc)
        self.shown_at = self.now - timedelta(minutes=1)
        self.shift.board_sent_at = self.shown_at
        self.shift.save(update_fields=["board_sent_at"])

    def add_template(self, title, planned_time, *, changed_at=None, **kwargs):
        template = TaskTemplate.objects.create(
            store=self.store, title=title, planned_time=planned_time, **kwargs
        )
        return self.touch(template, changed_at or self.now)

    def touch(self, template, at):
        """
        Ставит `updated_at` по часам теста.

        Поле объявлено с `auto_now`, поэтому save() записал бы настоящее «сейчас»,
        а тесты живут в выдуманном дне. `update()` идёт мимо `auto_now`.
        """
        TaskTemplate.objects.filter(pk=template.pk).update(updated_at=at)
        template.refresh_from_db()
        return template

    def test_new_task_inside_the_shift_resends_the_board(self):
        self.add_template("Count the till", time(15))

        refresh_changed_boards(self.now, client=self.client)

        self.assertEqual(len(self.client.sent), 1)
        message = self.client.sent[0]
        self.assertEqual(message["user_id"], self.employee_account.max_user_id)
        self.assertEqual(message["text"].splitlines()[0], "Список задач изменился")
        self.assertIn("○ 15:00 Count the till", message["text"])
        self.assertEqual(
            [row[0]["payload"] for row in message["buttons"]],
            [f"done:{TaskInstance.objects.get().id}"],
        )
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.board_sent_at, self.now)

    def test_does_not_resend_the_same_change_twice(self):
        self.add_template("Count the till", time(15))

        refresh_changed_boards(self.now, client=self.client)
        refresh_changed_boards(self.now + timedelta(seconds=30), client=self.client)

        self.assertEqual(len(self.client.sent), 1)

    def test_deleted_task_also_updates_the_board(self):
        template = self.add_template("Count the till", time(15))
        refresh_changed_boards(self.now, client=self.client)
        self.client.sent.clear()

        deleted_at = self.now + timedelta(seconds=30)
        template.is_active = False
        template.save(update_fields=["is_active"])
        self.touch(template, deleted_at)

        refresh_changed_boards(self.now + timedelta(minutes=1), client=self.client)

        self.assertEqual(len(self.client.sent), 1)
        self.assertNotIn("Count the till", self.client.sent[0]["text"])
        self.assertEqual(self.client.sent[0]["buttons"], [])

    def test_task_outside_the_shift_does_not_disturb_it(self):
        self.add_template("Closing", time(22))
        self.add_template("Other day", time(15), kind=TaskKind.ONE_TIME, on_date=date(2026, 9, 22))

        refresh_changed_boards(self.now, client=self.client)

        self.assertEqual(self.client.sent, [])

    def test_shift_that_never_saw_the_board_is_left_to_the_shift_start_message(self):
        self.shift.board_sent_at = None
        self.shift.save(update_fields=["board_sent_at"])
        self.add_template("Count the till", time(15))

        refresh_changed_boards(self.now, client=self.client)

        self.assertEqual(self.client.sent, [])

    def test_finished_shift_is_not_disturbed(self):
        self.add_template("Count the till", time(15))
        after_shift = datetime(2026, 9, 21, 15, tzinfo=timezone.utc)  # 18:00 по Москве

        refresh_changed_boards(after_shift, client=self.client)

        self.assertEqual(self.client.sent, [])


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


class ClosingNotificationsTests(TestCase):
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
        self.employee = Employee.objects.create(store=self.store, name="Anna")
        template = TaskTemplate.objects.create(
            store=self.store,
            title="Open store",
            planned_time=time(9),
            tolerance_minutes=15,
            requires_photo=False,
        )
        overdue_at = datetime(2026, 9, 21, 6, 16, tzinfo=timezone.utc)
        self.instance = TaskInstance.objects.create(
            template=template,
            date=date(2026, 9, 21),
            status=TaskStatus.OVERDUE,
            overdue_notified_at=overdue_at,
        )
        self.completed_at = datetime(2026, 9, 21, 6, 40, tzinfo=timezone.utc)
        self.client = RecordingClient()

    def complete(self):
        return mark_done(self.instance, self.employee, self.completed_at)

    def test_notifies_owner_with_lateness_and_deep_link_once(self):
        self.complete()
        notified_at = self.completed_at + timedelta(minutes=1)

        send_closing_notifications(notified_at, client=self.client)
        send_closing_notifications(notified_at + timedelta(seconds=30), client=self.client)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.closing_notified_at, notified_at)
        self.assertEqual(len(self.client.sent), 1)
        notification = self.client.sent[0]
        self.assertEqual(notification["user_id"], self.owner.max_user_id)
        self.assertEqual(
            notification["text"],
            (
                "Lenina, 14: задача «Open store» выполнена в 09:40, "
                "с опозданием на 40 минут. Кто отметил: Anna"
            ),
        )
        self.assertTrue(
            notification["buttons"][0][0]["url"].endswith(
                f"?startapp=store_{self.store.id}_20260921"
            )
        )

    def test_does_not_notify_without_completion_or_original_overdue_alert(self):
        send_closing_notifications(self.completed_at, client=self.client)
        self.assertEqual(self.client.sent, [])

        self.complete()
        self.instance.overdue_notified_at = None
        self.instance.save(update_fields=["overdue_notified_at"])
        send_closing_notifications(self.completed_at, client=self.client)
        self.assertEqual(self.client.sent, [])

    def test_failed_notification_is_retried_on_a_later_tick(self):
        self.complete()
        self.client.error = RuntimeError("MAX unavailable")

        with self.assertRaisesRegex(RuntimeError, "MAX unavailable"):
            send_closing_notifications(self.completed_at, client=self.client)

        self.instance.refresh_from_db()
        self.assertIsNone(self.instance.closing_notified_at)
        self.client.error = None
        send_closing_notifications(
            self.completed_at + timedelta(minutes=1),
            client=self.client,
        )
        self.instance.refresh_from_db()
        self.assertIsNotNone(self.instance.closing_notified_at)
        self.assertEqual(len(self.client.sent), 1)


@override_settings(SHIFT_BOUNDARY_TOLERANCE_MINUTES=5)
class ShiftSummariesTests(TestCase):
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
        self.account = MaxAccount.objects.create(max_user_id=101)
        self.employee = Employee.objects.create(
            store=self.store,
            name="Anna",
            account=self.account,
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
        self.summary_at = datetime(2026, 9, 21, 14, 5, tzinfo=timezone.utc)

    def make_instance(self, title, planned_time, **template_fields):
        template = TaskTemplate.objects.create(
            store=self.store,
            title=title,
            planned_time=planned_time,
            requires_photo=False,
            **template_fields,
        )
        return TaskInstance.objects.create(template=template, date=self.shift.date)

    def test_counts_only_collective_and_own_claimed_tasks_inside_shift(self):
        completed = self.make_instance("Opening", time(9))
        other = Employee.objects.create(store=self.store, name="Igor")
        mark_done(
            completed,
            other,
            datetime(2026, 9, 21, 6, 3, tzinfo=timezone.utc),
        )
        self.make_instance("Cleaning", time(11))
        own_claim = self.make_instance("Delivery", time(14), requires_claim=True)
        Claim.objects.create(instance=own_claim, employee=self.employee)
        other_claim = self.make_instance("Inventory", time(15), requires_claim=True)
        Claim.objects.create(instance=other_claim, employee=other)
        self.make_instance("Unclaimed cash count", time(16), requires_claim=True)
        self.make_instance("Closing", time(22))

        send_shift_summaries(self.summary_at, client=self.client)

        self.assertEqual(
            self.client.sent,
            [
                {
                    "user_id": self.account.max_user_id,
                    "text": (
                        "Смена завершена. Выполнено 1 из 3\n"
                        "Не отмечено: Cleaning, Delivery"
                    ),
                }
            ],
        )
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.summary_sent_at, self.summary_at)

    def test_waits_for_boundary_tolerance_and_sends_only_once(self):
        self.make_instance("Opening", time(9))

        send_shift_summaries(
            self.summary_at - timedelta(seconds=1),
            client=self.client,
        )
        self.assertEqual(self.client.sent, [])

        send_shift_summaries(self.summary_at, client=self.client)
        send_shift_summaries(
            self.summary_at + timedelta(seconds=30),
            client=self.client,
        )
        self.assertEqual(len(self.client.sent), 1)

    def test_empty_shift_still_receives_a_clear_zero_summary(self):
        send_shift_summaries(self.summary_at, client=self.client)

        self.assertEqual(
            self.client.sent,
            [
                {
                    "user_id": self.account.max_user_id,
                    "text": "Смена завершена. Выполнено 0 из 0",
                }
            ],
        )

    def test_draft_and_unbound_shifts_are_skipped(self):
        self.shift.status = ShiftStatus.DRAFT
        self.shift.save(update_fields=["status"])
        send_shift_summaries(self.summary_at, client=self.client)
        self.assertEqual(self.client.sent, [])

        self.shift.status = ShiftStatus.PUBLISHED
        self.shift.save(update_fields=["status"])
        self.employee.account = None
        self.employee.save(update_fields=["account"])
        send_shift_summaries(self.summary_at, client=self.client)
        self.assertEqual(self.client.sent, [])

    def test_failed_summary_is_available_for_retry(self):
        self.client.error = RuntimeError("MAX unavailable")

        with self.assertRaisesRegex(RuntimeError, "MAX unavailable"):
            send_shift_summaries(self.summary_at, client=self.client)

        self.shift.refresh_from_db()
        self.assertIsNone(self.shift.summary_sent_at)
        self.client.error = None
        send_shift_summaries(
            self.summary_at + timedelta(seconds=30),
            client=self.client,
        )
        self.shift.refresh_from_db()
        self.assertIsNotNone(self.shift.summary_sent_at)
        self.assertEqual(len(self.client.sent), 1)

    def test_does_not_send_stale_summary_on_a_later_day(self):
        send_shift_summaries(
            datetime(2026, 9, 22, 14, 5, tzinfo=timezone.utc),
            client=self.client,
        )

        self.assertEqual(self.client.sent, [])
        self.shift.refresh_from_db()
        self.assertIsNone(self.shift.summary_sent_at)


@override_settings(CLAIM_ESCALATION_MINUTES_BEFORE=15, REMINDER_MINUTES_BEFORE=5)
class ClaimSchedulerTests(TestCase):
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
        self.accounts = [
            MaxAccount.objects.create(max_user_id=101),
            MaxAccount.objects.create(max_user_id=102),
        ]
        self.employees = []
        for name, account in zip(("Anna", "Igor"), self.accounts):
            employee = Employee.objects.create(store=self.store, name=name, account=account)
            self.employees.append(employee)
            Shift.objects.create(
                employee=employee,
                store=self.store,
                date=date(2026, 9, 21),
                start_time=time(9),
                end_time=time(17),
                status=ShiftStatus.PUBLISHED,
            )
        self.template = TaskTemplate.objects.create(
            store=self.store,
            title="Delivery",
            planned_time=time(14),
            requires_photo=False,
            requires_claim=True,
        )
        self.instance = TaskInstance.objects.create(
            template=self.template,
            date=date(2026, 9, 21),
        )
        self.shift_start = datetime(2026, 9, 21, 6, tzinfo=timezone.utc)
        self.planned = datetime(2026, 9, 21, 11, tzinfo=timezone.utc)
        self.client = RecordingClient()

    def test_asks_each_responsible_employee_at_shift_start_only_once(self):
        send_claim_requests(self.shift_start, client=self.client)
        send_claim_requests(self.shift_start + timedelta(seconds=30), client=self.client)

        self.assertCountEqual(
            [message["user_id"] for message in self.client.sent],
            [account.max_user_id for account in self.accounts],
        )
        for message in self.client.sent:
            self.assertEqual(message["text"], "Сегодня в 14:00 delivery. Кто принимает?")
            self.assertEqual(
                message["buttons"][0][0]["payload"],
                f"claim:{self.instance.id}",
            )
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.reminder_sent_at, self.shift_start)
        self.assertEqual(self.instance.status, TaskStatus.REMINDED)

    def test_does_not_ask_before_first_responsible_shift_starts(self):
        send_claim_requests(self.shift_start - timedelta(seconds=1), client=self.client)

        self.assertEqual(self.client.sent, [])
        self.instance.refresh_from_db()
        self.assertIsNone(self.instance.reminder_sent_at)

    def test_regular_done_reminder_is_not_sent_to_entire_shift_for_claim_task(self):
        send_reminders(
            self.planned - timedelta(minutes=5),
            client=self.client,
        )

        self.assertEqual(self.client.sent, [])
        self.instance.refresh_from_db()
        self.assertIsNone(self.instance.reminder_sent_at)

    def test_escalates_to_shift_fifteen_minutes_before_deadline_once(self):
        escalation_at = self.planned - timedelta(minutes=15)

        escalate_unclaimed(escalation_at, client=self.client)
        escalate_unclaimed(escalation_at + timedelta(seconds=30), client=self.client)

        self.assertEqual(len(self.client.sent), 2)
        for message in self.client.sent:
            self.assertEqual(
                message["text"],
                "Delivery в 14:00 ещё никто не взял. Осталось 15 минут.",
            )
            self.assertEqual(
                message["buttons"][0][0]["payload"],
                f"claim:{self.instance.id}",
            )
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.escalation_sent_at, escalation_at)

    def test_notifies_owner_at_deadline_and_marks_task_unclaimed_once(self):
        escalate_unclaimed(self.planned, client=self.client)
        escalate_unclaimed(self.planned + timedelta(seconds=30), client=self.client)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.UNCLAIMED)
        self.assertEqual(self.instance.overdue_notified_at, self.planned)
        self.assertEqual(len(self.client.sent), 1)
        notification = self.client.sent[0]
        self.assertEqual(notification["user_id"], self.owner.max_user_id)
        self.assertEqual(
            notification["text"],
            "Lenina, 14: задачу «Delivery» в 14:00 никто не взял.",
        )
        self.assertTrue(
            notification["buttons"][0][0]["url"].endswith(
                f"?startapp=store_{self.store.id}_20260921"
            )
        )

    def test_claimed_task_is_not_escalated_or_reported_unclaimed(self):
        Claim.objects.create(instance=self.instance, employee=self.employees[0])

        escalate_unclaimed(
            self.planned - timedelta(minutes=15),
            client=self.client,
        )
        escalate_unclaimed(self.planned, client=self.client)

        self.instance.refresh_from_db()
        self.assertEqual(self.client.sent, [])
        self.assertIsNone(self.instance.escalation_sent_at)
        self.assertIsNone(self.instance.overdue_notified_at)

    def test_failed_owner_notification_remains_available_for_retry(self):
        self.client.error = RuntimeError("MAX unavailable")

        with self.assertRaisesRegex(RuntimeError, "MAX unavailable"):
            escalate_unclaimed(self.planned, client=self.client)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.SCHEDULED)
        self.assertIsNone(self.instance.overdue_notified_at)

    def test_does_not_send_stale_unclaimed_alert_on_a_later_day(self):
        escalate_unclaimed(
            self.planned + timedelta(days=1),
            client=self.client,
        )

        self.instance.refresh_from_db()
        self.assertEqual(self.client.sent, [])
        self.assertEqual(self.instance.status, TaskStatus.SCHEDULED)
        self.assertIsNone(self.instance.overdue_notified_at)


@override_settings(REMINDER_FIRST_MINUTES_BEFORE=15, REMINDER_FINAL_MINUTES_BEFORE=5)
class SendRemindersTests(TestCase):
    """
    Напоминания отсчитываются от срока задачи, то есть от планового времени плюс допуск.

    Задача стоит на 12:00 с допуском 15 минут, значит срок — 12:15 по Москве (09:15 UTC),
    первое напоминание в 12:00, последнее в 12:10.
    """

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
        self.deadline = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc)
        self.first_at = self.deadline - timedelta(minutes=15)
        self.final_at = self.deadline - timedelta(minutes=5)
        self.due_at = self.first_at

    def test_sends_first_reminder_with_done_button_and_marks_instance(self):
        send_reminders(self.first_at, client=self.client)

        self.assertEqual(len(self.client.sent), 1)
        self.assertEqual(self.client.sent[0]["user_id"], self.employee_account.max_user_id)
        self.assertEqual(
            self.client.sent[0]["text"],
            "Напоминание: «Opening store», плановое время 12:00.\n"
            "Осталось 15 минут: после 12:15 задача станет просроченной "
            "и о ней узнает владелец.",
        )
        self.assertEqual(
            self.client.sent[0]["buttons"][0][0]["payload"], f"done:{self.instance.id}"
        )
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.reminder_sent_at, self.first_at)
        self.assertIsNone(self.instance.final_reminder_sent_at)
        self.assertEqual(self.instance.status, TaskStatus.REMINDED)

    def test_sends_final_reminder_closer_to_the_deadline(self):
        send_reminders(self.first_at, client=self.client)
        send_reminders(self.final_at, client=self.client)

        self.assertEqual(len(self.client.sent), 2)
        self.assertEqual(
            self.client.sent[1]["text"],
            "Последнее напоминание: «Opening store», плановое время 12:00.\n"
            "Осталось 5 минут: после 12:15 задача станет просроченной "
            "и о ней узнает владелец.",
        )
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.reminder_sent_at, self.first_at)
        self.assertEqual(self.instance.final_reminder_sent_at, self.final_at)

    def test_final_reminder_closes_the_first_one_when_the_bot_was_down(self):
        """Слать «осталось 15 минут» задним числом уже незачем."""
        send_reminders(self.final_at, client=self.client)
        send_reminders(self.final_at + timedelta(minutes=1), client=self.client)

        self.assertEqual(len(self.client.sent), 1)
        self.assertTrue(self.client.sent[0]["text"].startswith("Последнее напоминание"))
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.reminder_sent_at, self.final_at)
        self.assertEqual(self.instance.final_reminder_sent_at, self.final_at)

    def test_does_not_send_the_same_reminder_twice(self):
        send_reminders(self.first_at, client=self.client)
        send_reminders(self.first_at, client=self.client)

        self.assertEqual(len(self.client.sent), 1)

    def test_completed_task_is_not_reminded_about(self):
        mark_done(self.instance, self.employee, self.first_at - timedelta(minutes=1))

        send_reminders(self.first_at, client=self.client)
        send_reminders(self.final_at, client=self.client)

        self.assertEqual(self.client.sent, [])

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

    def test_does_not_send_before_the_window_or_after_the_deadline(self):
        send_reminders(self.first_at - timedelta(seconds=1), client=self.client)
        self.assertEqual(self.client.sent, [])

        send_reminders(self.deadline, client=self.client)
        self.assertEqual(self.client.sent, [])
        self.instance.refresh_from_db()
        self.assertIsNone(self.instance.reminder_sent_at)
        self.assertIsNone(self.instance.final_reminder_sent_at)
