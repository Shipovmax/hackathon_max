from django.test import override_settings

from apps.core.models import MaxAccount, Role
from apps.core.tests.helpers import make_template

from .helpers import OwnerApiTestCase

REVIEW_TOKEN = "review-token-for-tests"
REVIEW_OWNER = 900000001


@override_settings(REVIEW_API_TOKEN=REVIEW_TOKEN, REVIEW_OWNER_MAX_ID=REVIEW_OWNER)
class ReviewTokenTests(OwnerApiTestCase):
    """Вход робота проверки хакатона: отдельный тестовый владелец, до чужих сетей не достаёт."""

    def review(self, method: str, path: str, data=None, token: str = REVIEW_TOKEN):
        return getattr(self.api, method)(
            f"/api{path}", data, format="json", HTTP_AUTHORIZATION=f"Bearer {token}"
        )

    def test_token_signs_in_as_the_test_owner_with_own_network(self):
        response = self.review("get", "/me/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["max_user_id"], body["role"]), (REVIEW_OWNER, "owner"))
        self.assertIsNotNone(body["network"])
        self.assertEqual(MaxAccount.objects.get(max_user_id=REVIEW_OWNER).role, Role.OWNER)

    def test_test_owner_does_not_see_the_real_network(self):
        make_template(self.store, "Opening", at=(9, 0))
        self.assertEqual(self.review("get", "/stores/").json(), [])
        self.assertEqual(self.review("get", f"/stores/{self.store.id}/day/").status_code, 404)
        self.assertEqual(self.review("get", f"/stores/{self.store.id}/task-templates/").status_code, 404)
        self.assertEqual(self.review("post", f"/employees/{self.anna.id}/dismiss/").status_code, 404)

    def test_test_owner_can_run_the_owner_scenario(self):
        created = self.review(
            "post", "/stores/", {"name": "Проверка", "open_time": "10:00", "close_time": "22:00"}
        )
        self.assertEqual(created.status_code, 201)
        store_id = created.json()["id"]
        task = self.review(
            "post", f"/stores/{store_id}/task-templates/", {"title": "Открытие", "planned_time": "10:00"}
        )
        self.assertEqual(task.status_code, 201)
        self.assertEqual(self.review("delete", f"/task-templates/{task.json()['id']}/").status_code, 204)

    def test_wrong_token_is_rejected(self):
        self.assertEqual(self.review("get", "/me/", token="guess").status_code, 401)

    def test_other_schemes_are_ignored(self):
        response = self.api.get("/api/me/", HTTP_AUTHORIZATION=f"Token {REVIEW_TOKEN}")
        self.assertEqual(response.status_code, 401)

    @override_settings(REVIEW_API_TOKEN="")
    def test_empty_setting_turns_the_entrance_off(self):
        self.assertEqual(self.review("get", "/me/", token="").status_code, 401)
        self.assertEqual(self.review("get", "/me/", token="anything").status_code, 401)
        self.assertFalse(MaxAccount.objects.filter(max_user_id=REVIEW_OWNER).exists())

    def test_mini_app_sign_in_still_works_next_to_it(self):
        response = self.call("get", "/me/")
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()["max_user_id"], REVIEW_OWNER)
