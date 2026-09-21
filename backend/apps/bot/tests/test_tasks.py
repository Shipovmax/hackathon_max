from datetime import date, datetime, time, timedelta, timezone
from tempfile import TemporaryDirectory
from unittest import mock

import httpx
from django.test import TestCase
from django.test.utils import override_settings

from apps.bot import texts
from apps.bot.handlers.tasks import on_claim, on_done, on_photo, on_status
from apps.core.domain.lifecycle import mark_done
from apps.core.models import (
    Claim,
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
        self.answer_buttons = []
        self.sent = []
        self.downloaded_urls = []
        self.download_result = b"test-image-bytes"
        self.download_error = None

    def answer_callback(self, callback_id, *, text, buttons=None):
        self.answers.append((callback_id, text))
        self.answer_buttons.append((callback_id, buttons))

    def send_message(self, **kwargs):
        self.sent.append(kwargs)

    def download_file(self, url):
        self.downloaded_urls.append(url)
        if self.download_error:
            raise self.download_error
        return self.download_result


class DoneCallbackTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)
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

    def test_does_not_open_a_second_photo_request_for_the_same_employee(self):
        self.template.requires_photo = True
        self.template.save(update_fields=["requires_photo"])
        self.call()
        second_template = TaskTemplate.objects.create(
            store=self.store,
            title="Prepare sales floor",
            planned_time=time(11),
            requires_photo=True,
        )
        second = TaskInstance.objects.create(template=second_template, date=DAY)

        self.call(instance_id=second.id)

        second.refresh_from_db()
        self.assertEqual(second.status, TaskStatus.SCHEDULED)
        self.assertIsNone(second.awaiting_photo_employee)
        self.assertEqual(
            self.client.answers[-1],
            ("callback-1", "Сначала пришлите фото для задачи «Open store»."),
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

    def photo_message(self, *, url="https://i.oneme.ru/photo", token="photo-token"):
        return {
            "body": {
                "attachments": [
                    {
                        "type": "image",
                        "payload": {"photo_id": 10, "token": token, "url": url},
                    }
                ]
            }
        }

    def reserve_photo(self):
        self.template.requires_photo = True
        self.template.save(update_fields=["requires_photo"])
        self.call()
        self.client.answers.clear()

    def send_photo(self, *, message=None, account=None, now=NOW + timedelta(minutes=1)):
        with mock.patch("apps.bot.handlers.tasks.timezone.now", return_value=now):
            on_photo(
                self.client,
                account or self.account,
                message or self.photo_message(),
            )

    def test_photo_is_downloaded_saved_and_completes_the_task(self):
        self.reserve_photo()

        self.send_photo()

        self.instance.refresh_from_db()
        completion = self.instance.completion
        self.assertEqual(self.instance.status, TaskStatus.DONE_ON_TIME)
        self.assertEqual(completion.employee, self.employee)
        self.assertEqual(completion.photo_token, "photo-token")
        with completion.photo.open("rb") as photo_file:
            self.assertEqual(photo_file.read(), b"test-image-bytes")
        self.assertEqual(self.client.downloaded_urls, ["https://i.oneme.ru/photo"])
        self.assertEqual(
            self.client.sent,
            [{"user_id": self.account.max_user_id, "text": "Open store отмечено в 10:04"}],
        )

    def test_download_failure_keeps_task_waiting_for_another_photo(self):
        self.reserve_photo()
        self.client.download_error = httpx.ConnectError(
            "CDN unavailable",
            request=httpx.Request("GET", "https://i.oneme.ru/photo"),
        )

        self.send_photo()

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.AWAITING_PHOTO)
        self.assertEqual(self.instance.awaiting_photo_employee, self.employee)
        self.assertFalse(hasattr(self.instance, "completion"))
        self.assertEqual(
            self.client.sent,
            [{"user_id": self.account.max_user_id, "text": texts.PHOTO_FAILED}],
        )

    def test_missing_photo_url_keeps_task_waiting(self):
        self.reserve_photo()

        self.send_photo(message=self.photo_message(url=""))

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.AWAITING_PHOTO)
        self.assertEqual(self.client.downloaded_urls, [])
        self.assertEqual(self.client.sent[0]["text"], texts.PHOTO_FAILED)

    def test_photo_without_pending_task_is_explained(self):
        self.send_photo()

        self.assertEqual(self.client.downloaded_urls, [])
        self.assertEqual(
            self.client.sent,
            [{"user_id": self.account.max_user_id, "text": texts.PHOTO_NOT_EXPECTED}],
        )

    def test_photo_from_another_employee_does_not_complete_reserved_task(self):
        self.reserve_photo()
        other_account = MaxAccount.objects.create(max_user_id=102)
        other = Employee.objects.create(store=self.store, name="Igor", account=other_account)
        self.make_shift(other, time(9), time(17))

        self.send_photo(account=other_account)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, TaskStatus.AWAITING_PHOTO)
        self.assertEqual(self.client.downloaded_urls, [])
        self.assertEqual(
            self.client.sent,
            [{"user_id": other_account.max_user_id, "text": texts.PHOTO_NOT_EXPECTED}],
        )


class StatusHandlerTests(TestCase):
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
        self.shift = self.make_shift(time(9), time(17))
        self.template = TaskTemplate.objects.create(
            store=self.store,
            title="Open store",
            planned_time=time(10),
            requires_photo=False,
        )
        self.instance = TaskInstance.objects.create(template=self.template, date=DAY)
        self.client = RecordingClient()

    def make_shift(self, start, end, *, day=DAY):
        return Shift.objects.create(
            employee=self.employee,
            store=self.store,
            date=day,
            start_time=start,
            end_time=end,
            status=ShiftStatus.PUBLISHED,
        )

    def make_instance(self, title, planned_time, **template_fields):
        template = TaskTemplate.objects.create(
            store=self.store,
            title=title,
            planned_time=planned_time,
            **template_fields,
        )
        return TaskInstance.objects.create(template=template, date=DAY)

    def call(self, *, account=None, now=NOW):
        with mock.patch("apps.bot.handlers.tasks.timezone.now", return_value=now):
            on_status(self.client, account or self.account)

    def test_lists_only_current_shift_tasks_with_computed_status_marks(self):
        completed = self.make_instance("Cleaning", time(9), requires_photo=False)
        mark_done(completed, self.employee, datetime(2026, 9, 21, 6, 1, tzinfo=timezone.utc))
        awaiting = self.make_instance("Photo report", time(9, 30), requires_photo=True)
        awaiting.status = TaskStatus.AWAITING_PHOTO
        awaiting.awaiting_photo_employee = self.employee
        awaiting.awaiting_photo_since = NOW
        awaiting.save(
            update_fields=["status", "awaiting_photo_employee", "awaiting_photo_since"]
        )
        self.make_instance("Prepare sales floor", time(11), requires_photo=False)
        self.make_instance("After shift", time(18), requires_photo=False)

        self.call()

        self.assertEqual(
            self.client.sent,
            [
                {
                    "user_id": self.account.max_user_id,
                    "text": (
                        "Задачи смены. Lenina, 14 · до 17:00\n\n"
                        "✓ 09:00 Cleaning\n"
                        "… 09:30 Photo report — ожидается фото\n"
                        "○ 10:00 Open store\n"
                        "○ 11:00 Prepare sales floor"
                    ),
                }
            ],
        )

    def test_hides_claim_task_taken_by_another_employee(self):
        other = Employee.objects.create(store=self.store, name="Igor")
        claimed = self.make_instance(
            "Delivery",
            time(12),
            requires_photo=False,
            requires_claim=True,
        )
        Claim.objects.create(instance=claimed, employee=other)

        self.call()

        self.assertNotIn("Delivery", self.client.sent[0]["text"])
        self.assertIn("Open store", self.client.sent[0]["text"])

    def test_reports_future_shift_instead_of_tasks(self):
        self.shift.start_time = time(14)
        self.shift.end_time = time(22)
        self.shift.save(update_fields=["start_time", "end_time"])

        self.call()

        self.assertEqual(
            self.client.sent[0]["text"],
            "Ваша смена сегодня с 14:00. Задачи появятся после начала смены.",
        )

    def test_reports_ended_shift_instead_of_tasks(self):
        self.shift.start_time = time(8)
        self.shift.end_time = time(9)
        self.shift.save(update_fields=["start_time", "end_time"])

        self.call()

        self.assertEqual(
            self.client.sent[0]["text"],
            "Ваша смена завершилась в 09:00. Итог придёт отдельным сообщением.",
        )

    def test_reports_day_off_and_next_shift(self):
        self.shift.delete()
        self.make_shift(time(9), time(17), day=DAY + timedelta(days=1))

        self.call()

        self.assertEqual(
            self.client.sent[0]["text"],
            "Сегодня у вас выходной. Ближайшая смена — завтра с 09:00",
        )

    def test_boundary_tolerance_counts_as_current_shift(self):
        before_start = datetime(2026, 9, 21, 5, 56, tzinfo=timezone.utc)

        self.call(now=before_start)

        self.assertIn("Задачи смены.", self.client.sent[0]["text"])

    def test_active_shift_without_tasks_has_a_clear_message(self):
        self.template.is_active = False
        self.template.save(update_fields=["is_active"])

        self.call()

        self.assertEqual(
            self.client.sent[0]["text"],
            "Задачи смены. Lenina, 14 · до 17:00\n\nЗадач на эту смену нет.",
        )

    def test_unbound_account_is_asked_for_invite_code(self):
        unbound = MaxAccount.objects.create(max_user_id=999)

        self.call(account=unbound)

        self.assertEqual(
            self.client.sent,
            [{"user_id": unbound.max_user_id, "text": texts.ROLE_EMPLOYEE_ASK_CODE}],
        )


class ClaimHandlerTests(TestCase):
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
        self.anna_account = MaxAccount.objects.create(max_user_id=101)
        self.anna = Employee.objects.create(
            store=self.store,
            name="Anna",
            account=self.anna_account,
        )
        self.igor_account = MaxAccount.objects.create(max_user_id=102)
        self.igor = Employee.objects.create(
            store=self.store,
            name="Igor",
            account=self.igor_account,
        )
        for employee in (self.anna, self.igor):
            Shift.objects.create(
                employee=employee,
                store=self.store,
                date=DAY,
                start_time=time(9),
                end_time=time(17),
                status=ShiftStatus.PUBLISHED,
            )
        template = TaskTemplate.objects.create(
            store=self.store,
            title="Delivery",
            planned_time=time(14),
            requires_photo=False,
            requires_claim=True,
        )
        self.instance = TaskInstance.objects.create(template=template, date=DAY)
        self.client = RecordingClient()

    def claim(self, account, callback_id="claim-callback"):
        with mock.patch("apps.bot.handlers.tasks.timezone.now", return_value=NOW):
            on_claim(self.client, account, callback_id, self.instance.id)

    def test_first_employee_claims_task_and_others_are_told(self):
        self.claim(self.anna_account)

        claim = Claim.objects.get(instance=self.instance)
        self.assertEqual(claim.employee, self.anna)
        self.assertEqual(
            self.client.answers,
            [("claim-callback", texts.claim_confirmed())],
        )
        self.assertEqual(
            self.client.answer_buttons[0][1][0][0]["payload"],
            f"done:{self.instance.id}",
        )
        self.assertEqual(
            self.client.sent,
            [
                {
                    "user_id": self.igor_account.max_user_id,
                    "text": "Delivery в 14:00 выполняет Anna.",
                }
            ],
        )

    def test_second_employee_sees_who_already_claimed_task(self):
        self.claim(self.anna_account, "first")
        self.client.answers.clear()
        self.client.answer_buttons.clear()
        self.client.sent.clear()

        self.claim(self.igor_account, "second")

        self.assertEqual(Claim.objects.filter(instance=self.instance).count(), 1)
        self.assertEqual(
            self.client.answers,
            [("second", "Delivery в 14:00 выполняет Anna.")],
        )
        self.assertEqual(self.client.answer_buttons, [("second", None)])
        self.assertEqual(self.client.sent, [])

    def test_employee_without_shift_covering_task_cannot_claim(self):
        Shift.objects.filter(employee=self.anna).update(start_time=time(15), end_time=time(20))

        self.claim(self.anna_account)

        self.assertFalse(Claim.objects.filter(instance=self.instance).exists())
        self.assertEqual(
            self.client.answers,
            [("claim-callback", texts.CLAIM_NOT_AVAILABLE)],
        )

    def test_claim_task_can_only_be_completed_by_the_winner(self):
        with mock.patch("apps.bot.handlers.tasks.timezone.now", return_value=NOW):
            on_done(self.client, self.anna_account, "before-claim", self.instance.id)
        self.assertEqual(self.client.answers[-1], ("before-claim", texts.CLAIM_REQUIRED))

        self.claim(self.anna_account)
        with mock.patch("apps.bot.handlers.tasks.timezone.now", return_value=NOW):
            on_done(self.client, self.igor_account, "wrong", self.instance.id)
            on_done(self.client, self.anna_account, "winner", self.instance.id)

        self.assertIn(("wrong", "Delivery в 14:00 выполняет Anna."), self.client.answers)
        self.assertIn(("winner", "Delivery отмечено в 10:03"), self.client.answers)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.completion.employee, self.anna)
