from datetime import time

from django.test import SimpleTestCase, TestCase

from apps.bot import keyboards, texts
from apps.bot.handlers.onboarding import bind_by_code, on_role_chosen
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

    def test_reminder_matches_agreed_wording(self):
        self.assertEqual(texts.reminder(5, "Открытие магазина"), "Через 5 минут — открытие магазина")

    def test_parse_callback(self):
        self.assertEqual(keyboards.parse_callback("done:42"), ("done", "42"))
        self.assertEqual(keyboards.parse_callback(""), ("", ""))


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
