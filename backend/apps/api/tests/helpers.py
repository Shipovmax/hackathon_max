import hashlib
import hmac
import json
import time
from unittest import mock
from urllib.parse import quote

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import Employee, Network
from apps.core.tests.helpers import make_network, make_store, moscow

TOKEN = "test-bot-token"
OWNER_ID = 1001


def signed_init_data(user_id: int) -> str:
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "test-query-id",
        "user": json.dumps({"id": user_id, "first_name": "Max"}, separators=(",", ":")),
    }
    launch = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, launch.encode(), hashlib.sha256).hexdigest()
    encoded = "&".join(f"{k}={quote(params[k], safe='')}" for k in sorted(params))
    return f"{encoded}&hash={digest}"


@override_settings(BOT_TOKEN=TOKEN)
class OwnerApiTestCase(TestCase):
    """An owner with one store and two employees; requests are signed like MAX signs a mini-app launch."""

    def setUp(self):
        self.network: Network = make_network(OWNER_ID)
        self.store = make_store(self.network)
        self.anna = Employee.objects.create(store=self.store, name="Anna")
        self.igor = Employee.objects.create(store=self.store, name="Igor")
        self.api = APIClient()

    def call(self, method: str, path: str, data=None, user_id: int = OWNER_ID):
        return getattr(self.api, method)(
            f"/api{path}", data, format="json", HTTP_X_MAX_INIT_DATA=signed_init_data(user_id)
        )

    def other_owner(self):
        """Another owner with their own store, to check that networks stay separated."""
        network = make_network(2002, "Other network")
        return make_store(network, "Foreign store")

    @staticmethod
    def at(hour: int, minute: int = 0, day=None):
        """Freeze the server clock at a Moscow wall-clock time."""
        return mock.patch("django.utils.timezone.now", return_value=moscow(hour, minute, day))
