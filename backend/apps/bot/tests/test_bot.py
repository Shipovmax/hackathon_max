from datetime import time
from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.bot import keyboards, texts
from apps.bot.handlers.onboarding import bind_by_code, on_role_chosen
from apps.bot.max_api.client import MaxClient
from apps.core.models import Employee, InviteCode, MaxAccount, Network, Role, Store


class FakeClient:
    def __init__(self):
        self.calls = []

    def answer_callback(self, callback_id, *, text):
        self.calls.append(("answer", callback_id, text))

    def send_message(self, **kwargs):
        self.calls.append(("send", kwargs))


class TextsTests(SimpleTestCase):
    def test_minutes_plural(self):
        self.assertEqual(texts.minutes(1), "1 минуту")
        self.assertEqual(texts.minutes(5), "5 минут")
        self.assertEqual(texts.minutes(22), "22 минуты")
        self.assertEqual(texts.minutes(11), "11 минут")

    def test_tasks_word_uses_the_genitive_after_a_count(self):
        self.assertEqual(texts.tasks_word(1), "задачи")
        self.assertEqual(texts.tasks_word(3), "задач")
        self.assertEqual(texts.tasks_word(11), "задач")

    def test_reminder_names_the_task_and_the_deadline(self):
        self.assertEqual(
            texts.reminder("Открытие магазина", "09:00", "09:15", 15, False),
            "Напоминание: «Открытие магазина», плановое время 09:00.\n"
            "Осталось 15 минут: после 09:15 задача станет просроченной "
            "и о ней узнает владелец.",
        )

    def test_final_reminder_is_marked_as_the_last_one(self):
        self.assertTrue(
            texts.reminder("Открытие магазина", "09:00", "09:15", 5, True).startswith(
                "Последнее напоминание"
            )
        )

    def test_planned_time_reminder_names_the_target(self):
        self.assertEqual(
            texts.planned_time_reminder("Открытие магазина", "09:00", 15, False),
            "Напоминание: «Открытие магазина», плановое время 09:00.\n"
            "Осталось 15 минут до планового времени.",
        )

    def test_final_planned_time_reminder_is_scoped_to_planned_time(self):
        self.assertTrue(
            texts.planned_time_reminder("Открытие магазина", "09:00", 5, True).startswith(
                "Последнее напоминание до планового времени"
            )
        )

    def test_photo_request_names_the_task(self):
        text = texts.ask_photo_for("Открытие магазина", "09:00", "09:15", 10)
        self.assertIn("Задача «Открытие магазина», плановое время 09:00.", text)
        self.assertIn("задача принимается до 09:15", text)
        self.assertIn("не придёт за 10 минут", text)

    def test_parse_callback(self):
        self.assertEqual(keyboards.parse_callback("done:42"), ("done", "42"))
        self.assertEqual(keyboards.parse_callback(""), ("", ""))


class MaxClientTests(SimpleTestCase):
    def test_callback_answer_can_replace_keyboard(self):
        client = object.__new__(MaxClient)
        client._request = mock.Mock(return_value={})
        buttons = keyboards.done_button(42)

        client.answer_callback("callback-1", text="Task is yours", buttons=buttons)

        client._request.assert_called_once_with(
            "POST",
            "/answers",
            params={"callback_id": "callback-1"},
            json={
                "message": {
                    "text": "Task is yours",
                    "attachments": [
                        {"type": "inline_keyboard", "payload": {"buttons": buttons}}
                    ],
                }
            },
        )


class OnboardingTests(TestCase):
    def setUp(self):
        owner = MaxAccount.objects.create(max_user_id=1, role=Role.OWNER)
        network = Network.objects.create(owner=owner, name="Test network")
        store = Store.objects.create(
            network=network, name="Lenina, 14", open_time=time(9), close_time=time(22)
        )
        self.employee = Employee.objects.create(store=store, name="Anna")
        self.invite = InviteCode.issue(self.employee)

    def test_code_binds_account_once(self):
        account = MaxAccount.objects.create(max_user_id=2, role=Role.EMPLOYEE)
        bound = bind_by_code(account, f" {self.invite.code.lower()} ")
        self.assertEqual(bound, self.employee)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.account, account)

        other = MaxAccount.objects.create(max_user_id=3, role=Role.EMPLOYEE)
        self.assertIsNone(bind_by_code(other, self.invite.code))

    def test_unknown_code_is_rejected(self):
        account = MaxAccount.objects.create(max_user_id=2, role=Role.EMPLOYEE)
        self.assertIsNone(bind_by_code(account, "NOPE1234"))

    def test_role_choice_is_saved(self):
        account = MaxAccount.objects.create(max_user_id=5)
        client = FakeClient()
        on_role_chosen(client, account, "cb-1", "employee")
        account.refresh_from_db()
        self.assertEqual(account.role, Role.EMPLOYEE)
        self.assertEqual(client.calls[0], ("answer", "cb-1", texts.ROLE_EMPLOYEE_ASK_CODE))

    def test_owner_role_creates_network_once(self):
        account = MaxAccount.objects.create(max_user_id=7)
        on_role_chosen(FakeClient(), account, "cb-3", "owner")
        on_role_chosen(FakeClient(), account, "cb-4", "owner")
        self.assertEqual(Network.objects.filter(owner=account).count(), 1)

    def test_unknown_role_is_ignored(self):
        account = MaxAccount.objects.create(max_user_id=6)
        on_role_chosen(FakeClient(), account, "cb-2", "admin")
        account.refresh_from_db()
        self.assertEqual(account.role, "")
