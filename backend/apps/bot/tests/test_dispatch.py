from datetime import time
from unittest import mock

from django.test import TestCase

from apps.bot import texts
from apps.bot.dispatcher import dispatch
from apps.core.models import Employee, MaxAccount, Network, Role, Store

USER = {"user_id": 5001, "first_name": "Test", "is_bot": False, "name": "Test"}
BOT = {"user_id": 9001, "is_bot": True, "name": "Bot", "username": "test_bot"}
DIALOG = {"chat_type": "dialog", "chat_id": 700, "user_id": 9001}
PHOTO = [{"type": "image", "payload": {"photo_id": 1, "token": "t", "url": "https://i.oneme.ru/i?r=x"}}]


class RecordingClient:
    def __init__(self):
        self.sent = []
        self.answers = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)

    def answer_callback(self, callback_id, *, text):
        self.answers.append((callback_id, text))


def bot_started():
    return {"update_type": "bot_started", "chat_id": 700, "user": USER, "user_id": 5001, "user_locale": "ru"}


def callback(payload):
    return {
        "update_type": "message_callback",
        "callback": {"callback_id": "cb-1", "payload": payload, "user": USER},
        "message": {"recipient": DIALOG, "sender": BOT, "body": {"mid": "m1", "text": "x", "attachments": []}},
    }


def message(text="", attachments=None, sender=USER):
    return {
        "update_type": "message_created",
        "message": {
            "sender": sender,
            "recipient": DIALOG,
            "body": {"mid": "m2", "text": text, "attachments": attachments or []},
        },
    }


class DispatchTests(TestCase):
    def setUp(self):
        self.client = RecordingClient()

    def test_bot_started_stores_account_and_asks_role(self):
        dispatch(self.client, bot_started())
        account = MaxAccount.objects.get(max_user_id=5001)
        self.assertEqual(account.dialog_chat_id, 700)
        self.assertEqual(self.client.sent[0]["text"], texts.ROLE_PROMPT)
        buttons = self.client.sent[0]["buttons"][0]
        self.assertEqual([b["payload"] for b in buttons], ["role:owner", "role:employee"])

    def test_owner_callback_sets_role_creates_network_and_offers_app(self):
        dispatch(self.client, callback("role:owner"))
        account = MaxAccount.objects.get(max_user_id=5001)
        self.assertEqual(account.role, Role.OWNER)
        self.assertTrue(Network.objects.filter(owner=account).exists())
        self.assertEqual(self.client.answers, [("cb-1", texts.ROLE_OWNER_CHOSEN)])
        self.assertEqual(self.client.sent[0]["buttons"][0][0]["type"], "link")

    def test_restart_asks_unbound_employee_for_the_code(self):
        MaxAccount.objects.create(max_user_id=5001, role=Role.EMPLOYEE)
        dispatch(self.client, bot_started())
        self.assertEqual(self.client.sent[0]["text"], texts.ROLE_EMPLOYEE_ASK_CODE)

    def test_role_command_asks_role_again(self):
        MaxAccount.objects.create(max_user_id=5001, role=Role.EMPLOYEE)
        dispatch(self.client, message("/role"))
        self.assertEqual(self.client.sent[0]["text"], texts.ROLE_PROMPT)

    def test_employee_photo_is_routed_to_task_handler(self):
        MaxAccount.objects.create(max_user_id=5001, role=Role.EMPLOYEE)
        with mock.patch("apps.bot.handlers.tasks.on_photo") as on_photo:
            dispatch(self.client, message(attachments=PHOTO))
        on_photo.assert_called_once()

    def bind_owner_as_employee(self):
        account = MaxAccount.objects.create(max_user_id=5001, role=Role.OWNER)
        network = Network.objects.create(owner=account, name="Mine")
        store = Store.objects.create(network=network, name="Lenina, 14", open_time=time(9), close_time=time(22))
        Employee.objects.create(store=store, name="Owner", account=account)

    def test_bound_owner_can_send_a_photo_without_switching_role(self):
        self.bind_owner_as_employee()
        with mock.patch("apps.bot.handlers.tasks.on_photo") as on_photo:
            dispatch(self.client, message(attachments=PHOTO))
        on_photo.assert_called_once()

    def test_bound_owner_can_ask_what_is_left(self):
        self.bind_owner_as_employee()
        with mock.patch("apps.bot.handlers.tasks.on_status") as on_status:
            dispatch(self.client, message("что осталось"))
        on_status.assert_called_once()

    def test_owner_text_is_not_taken_for_an_invite_code(self):
        MaxAccount.objects.create(max_user_id=5001, role=Role.OWNER)
        with mock.patch("apps.bot.handlers.onboarding.reply_to_code") as reply_to_code:
            dispatch(self.client, message("ABCD1234"))
        reply_to_code.assert_not_called()
        self.assertEqual(self.client.sent[0]["text"], texts.UNKNOWN)

    def test_unknown_callback_is_answered(self):
        dispatch(self.client, callback("nope:1"))
        self.assertEqual(self.client.answers, [("cb-1", texts.UNKNOWN)])

    def test_messages_from_bots_are_ignored(self):
        dispatch(self.client, message("hello", sender=BOT))
        self.assertEqual(self.client.sent, [])
        self.assertFalse(MaxAccount.objects.exists())
