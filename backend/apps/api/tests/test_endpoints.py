import hashlib
import hmac
import json
import time
from urllib.parse import quote

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import MaxAccount, Role

TOKEN = "test-bot-token"


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
class ApiEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_is_public(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_protected_endpoint_without_init_data_is_unauthorized(self):
        self.assertEqual(self.client.get("/api/me/").status_code, 401)

    def test_invalid_init_data_is_unauthorized(self):
        response = self.client.get("/api/me/", HTTP_X_MAX_INIT_DATA="user=%7B%7D&hash=bad")
        self.assertEqual(response.status_code, 401)

    def test_owner_gets_profile(self):
        MaxAccount.objects.create(max_user_id=111, first_name="Max", role=Role.OWNER)
        response = self.client.get("/api/me/", HTTP_X_MAX_INIT_DATA=signed_init_data(111))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "owner")
        self.assertIsNone(response.json()["network"])

    def test_employee_is_forbidden_with_code(self):
        MaxAccount.objects.create(max_user_id=222, role=Role.EMPLOYEE)
        response = self.client.get("/api/me/", HTTP_X_MAX_INIT_DATA=signed_init_data(222))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "not_owner")

    def test_unknown_account_is_created_without_role_and_forbidden(self):
        response = self.client.get("/api/me/", HTTP_X_MAX_INIT_DATA=signed_init_data(333))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(MaxAccount.objects.filter(max_user_id=333, role="").exists())

    def test_stub_endpoint_reports_not_implemented(self):
        MaxAccount.objects.create(max_user_id=444, role=Role.OWNER)
        response = self.client.get("/api/dashboard/", HTTP_X_MAX_INIT_DATA=signed_init_data(444))
        self.assertEqual(response.status_code, 501)
