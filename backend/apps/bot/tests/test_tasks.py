from datetime import date, datetime, time, timedelta, timezone
from unittest import mock

from django.test import TestCase

from apps.bot import texts
from apps.bot.handlers.tasks import on_done
from apps.core.domain.lifecycle import mark_done
from apps.core.models import (
    Employee,
    MaxAccount,
    Network,
    Shift,
    ShiftStatus,
    Store,
    TaskInstance,
    TaskStatus,
    TaskTemplate,
)


DAY = date(2026, 9, 21)
NOW = datetime(2026, 9, 21, 7, 3, tzinfo=timezone.utc)  # 10:03 in Moscow


class RecordingClient:
    def __init__(self):
        self.answers = []

    def answer_callback(self, callback_id, *, text):
        self.answers.append((callback_id, text))


class DoneCallbackTests(TestCase):
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
        self.shift = self.make_shift(self.employee, time(9), time(17))
        self.template = TaskTemplate.objects.create(
            store=self.store,
            title="Open store",
            planned_time=time(10),
            requires_photo=False,
        )
        self.instance = TaskInstance.objects.create(template=self.template, date=DAY)
        self.client = RecordingClient()

    def make_shift(self, employee, start, end, *, day=DAY):
        return Shift.objects.create(
            employee=employee,
            store=self.store,
            date=day,
            start_time=start,
            end_time=end,
            status=ShiftStatus.PUBLISHED,
        )

    def call(self, instance_id=None, now=NOW):
        with mock.patch("apps.bot.handlers.tasks.timezone.now", return_value=now):
            on_done(
                self.client,
                self.account,
                "callback-1",
                instance_id or self.instance.id,
            )

    def test_marks_task_and_shows_next_unfinished_task_in_current_shift(self):
        next_template = TaskTemplate.objects.create(
            store=self.store,
            title="Prepare sales floor",
            planned_time=time(11),
            requires_photo=False,
        )
        TaskInstance.objects.create(template=next_template, date=DAY)

        self.call()

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.DONE_ON_TIME)
        self.assertEqual(self.instance.completion.employee, self.employee)
        self.assertEqual(self.instance.completion.completed_at, NOW)
        self.assertEqual(
            self.client.answers,
            [("callback-1", "Open store отмечено в 10:03. Следующая задача — в 11:00")],
        )

    def test_reserves_task_and_requests_photo(self):
        self.template.requires_photo = True
        self.template.photo_prompt = "Пришлите фото торгового зала"
        self.template.save(update_fields=["requires_photo", "photo_prompt"])

        self.call()

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.AWAITING_PHOTO)
        self.assertEqual(self.instance.awaiting_photo_employee, self.employee)
        self.assertEqual(self.instance.awaiting_photo_since, NOW)
        self.assertFalse(hasattr(self.instance, "completion"))
        self.assertEqual(
            self.client.answers,
            [("callback-1", "Пришлите фото торгового зала")],
        )

    def test_repeated_photo_request_keeps_the_same_employee(self):
        self.template.requires_photo = True
        self.template.save(update_fields=["requires_photo"])
        self.call()
        self.instance.refresh_from_db()
        first_requested_at = self.instance.awaiting_photo_since

        self.call(now=NOW + timedelta(minutes=1))

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.awaiting_photo_employee, self.employee)
        self.assertEqual(self.instance.awaiting_photo_since, first_requested_at)
        self.assertEqual(len(self.client.answers), 2)

    def test_does_not_let_another_employee_replace_pending_photo_owner(self):
        self.template.requires_photo = True
        self.template.save(update_fields=["requires_photo"])
        other_account = MaxAccount.objects.create(max_user_id=102)
        other = Employee.objects.create(store=self.store, name="Igor", account=other_account)
        self.make_shift(other, time(9), time(17))
        self.instance.status = TaskStatus.AWAITING_PHOTO
        self.instance.awaiting_photo_employee = other
        self.instance.awaiting_photo_since = NOW
        self.instance.save(
            update_fields=["status", "awaiting_photo_employee", "awaiting_photo_since"]
        )

        self.call()

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.awaiting_photo_employee, other)
        self.assertEqual(
            self.client.answers,
            [("callback-1", "Задача «Open store» уже ожидает фото от Igor.")],
        )

    def test_day_off_names_the_next_shift(self):
        self.shift.delete()
        self.make_shift(self.employee, time(9), time(17), day=DAY + timedelta(days=1))

        self.call()

        self.assertEqual(
            self.client.answers,
            [("callback-1", "Сегодня у вас выходной. Ближайшая смена — завтра с 09:00")],
        )

    def test_not_started_names_the_shift_that_can_mark_now(self):
        self.shift.start_time = time(14)
        self.shift.end_time = time(22)
        self.shift.save(update_fields=["start_time", "end_time"])
        other = Employee.objects.create(store=self.store, name="Igor")
        self.make_shift(other, time(9), time(17))

        self.call()

        self.assertEqual(
            self.client.answers,
            [
                (
                    "callback-1",
                    "Ваша смена сегодня с 14:00. "
                    "Отметить open store может тот, кто работает с 09:00.",
                )
            ],
        )

    def test_ended_names_the_employee_who_can_mark_now(self):
        self.shift.start_time = time(8)
        self.shift.end_time = time(9)
        self.shift.save(update_fields=["start_time", "end_time"])
        other = Employee.objects.create(store=self.store, name="Igor")
        self.make_shift(other, time(9), time(17))

        self.call()

        self.assertEqual(
            self.client.answers,
            [("callback-1", "Ваша смена завершилась в 09:00. Open store отметит Igor.")],
        )

    def test_already_done_names_employee_and_time(self):
        other = Employee.objects.create(store=self.store, name="Igor")
        mark_done(self.instance, other, NOW - timedelta(minutes=2))

        self.call()

        self.assertEqual(
            self.client.answers,
            [("callback-1", "Open store отметил Igor в 10:01.")],
        )

    def test_unbound_account_is_asked_for_invite_code(self):
        account = MaxAccount.objects.create(max_user_id=999)

        with mock.patch("apps.bot.handlers.tasks.timezone.now", return_value=NOW):
            on_done(self.client, account, "callback-1", self.instance.id)

        self.assertEqual(
            self.client.answers,
            [("callback-1", texts.ROLE_EMPLOYEE_ASK_CODE)],
        )

    def test_unknown_task_is_answered_without_error(self):
        self.call(instance_id=999)

        self.assertEqual(self.client.answers, [("callback-1", texts.UNKNOWN)])
