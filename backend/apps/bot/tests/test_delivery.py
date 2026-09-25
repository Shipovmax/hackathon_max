from datetime import date, datetime, time, timedelta, timezone
from unittest import mock

import httpx
from django.test import TestCase

from apps.bot import scheduler
from apps.bot.max_api.client import MaxApiError
from apps.bot.scheduler import mark_overdue
from apps.core.models import MaxAccount, Network, Store, TaskInstance, TaskStatus, TaskTemplate

DAY = date(2026, 9, 21)
AFTER_DEADLINE = datetime(2026, 9, 21, 6, 16, tzinfo=timezone.utc)


class FlakyClient:
    def __init__(self, failing_user: int, error: Exception):
        self.failing_user = failing_user
        self.error = error
        self.sent = []

    def send_message(self, **kwargs):
        if kwargs.get("user_id") == self.failing_user:
            raise self.error
        self.sent.append(kwargs)
        return {"message": {"body": {"mid": "mid"}}}


class DeliveryFailureTests(TestCase):
    def setUp(self):
        self.blocked = self.open_task(owner_id=1, store_name="Lenina, 14")
        self.healthy = self.open_task(owner_id=2, store_name="Gagarina, 3")

    @staticmethod
    def open_task(owner_id: int, store_name: str) -> TaskInstance:
        owner = MaxAccount.objects.create(max_user_id=owner_id)
        network = Network.objects.create(owner=owner, name=f"Network {owner_id}")
        store = Store.objects.create(
            network=network, name=store_name, open_time=time(9), close_time=time(22), timezone="Europe/Moscow"
        )
        template = TaskTemplate.objects.create(
            store=store, title="Open store", planned_time=time(9), tolerance_minutes=15, requires_photo=False
        )
        return TaskInstance.objects.create(template=template, date=DAY)

    def test_refused_recipient_is_not_retried_and_others_still_get_notified(self):
        client = FlakyClient(failing_user=1, error=MaxApiError(403, "chat.denied"))
        mark_overdue(AFTER_DEADLINE, client=client)

        self.blocked.refresh_from_db()
        self.healthy.refresh_from_db()
        self.assertEqual(self.blocked.status, TaskStatus.OVERDUE)
        self.assertIsNotNone(self.blocked.overdue_notified_at)
        self.assertEqual(self.healthy.status, TaskStatus.OVERDUE)
        self.assertEqual([m["user_id"] for m in client.sent], [2])

        mark_overdue(AFTER_DEADLINE + timedelta(seconds=30), client=client)
        self.assertEqual(len(client.sent), 1)

    def test_temporary_outage_is_retried_later_without_blocking_others(self):
        for error in (MaxApiError(503, "unavailable"), MaxApiError(429, "slow down"), httpx.ConnectError("down")):
            with self.subTest(error=error):
                TaskInstance.objects.update(status=TaskStatus.SCHEDULED, overdue_notified_at=None)
                client = FlakyClient(failing_user=1, error=error)
                mark_overdue(AFTER_DEADLINE, client=client)

                self.blocked.refresh_from_db()
                self.assertIsNone(self.blocked.overdue_notified_at)
                self.assertEqual([m["user_id"] for m in client.sent], [2])

                client.failing_user = None
                mark_overdue(AFTER_DEADLINE + timedelta(seconds=30), client=client)
                self.blocked.refresh_from_db()
                self.assertIsNotNone(self.blocked.overdue_notified_at)

    def test_a_failing_step_does_not_stop_the_rest_of_the_tick(self):
        ran = []

        def broken(now):
            raise ValueError("bad data in one store")

        def healthy(now):
            ran.append(now)

        broken.__name__, healthy.__name__ = "broken", "healthy"
        with mock.patch.object(scheduler, "STEPS", (broken, healthy)), self.assertLogs("apps.bot.scheduler", "ERROR"):
            scheduler.tick(AFTER_DEADLINE)
        self.assertEqual(ran, [AFTER_DEADLINE])
