from apps.core.models import Employee, Store
from apps.core.tests.helpers import make_template

from .helpers import OWNER_ID, OwnerApiTestCase, signed_init_data

DRAFT = {"week_start": "2026-09-21", "shifts": []}


class BadInputTests(OwnerApiTestCase):
    def setUp(self):
        super().setUp()
        self.template = make_template(self.store, "Opening", at=(9, 0))

    def raw(self, method: str, path: str, body: str):
        return getattr(self.api, method)(
            f"/api{path}", body, content_type="application/json", HTTP_X_MAX_INIT_DATA=signed_init_data(OWNER_ID)
        )

    def test_body_that_is_not_an_object_is_rejected(self):
        writes = [
            ("post", "/stores/"),
            ("patch", f"/stores/{self.store.id}/"),
            ("post", f"/stores/{self.store.id}/employees/"),
            ("post", f"/stores/{self.store.id}/task-templates/"),
            ("patch", f"/task-templates/{self.template.id}/"),
            ("put", f"/stores/{self.store.id}/schedule/"),
            ("post", f"/stores/{self.store.id}/schedule/coverage/"),
            ("post", f"/stores/{self.store.id}/schedule/publish/"),
        ]
        for method, path in writes:
            for body in ("[]", "123", "null", '"text"'):
                with self.subTest(method=method, path=path, body=body):
                    response = self.raw(method, path, body)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json()["detail"], "Тело запроса должно быть JSON-объектом")

    def test_employee_id_of_a_wrong_type_is_rejected(self):
        for bad in ([], {}, "1", True, 1.5):
            shift = {"employee_id": bad, "date": "2026-09-22", "start": "10:00", "end": "18:00"}
            with self.subTest(employee_id=bad):
                response = self.call("post", f"/stores/{self.store.id}/schedule/coverage/", {**DRAFT, "shifts": [shift]})
                self.assertEqual(response.status_code, 400)

    def test_dates_at_the_edge_of_the_calendar_are_rejected(self):
        for day in ("9999-12-31", "0001-01-01", "1999-12-31"):
            with self.subTest(day=day):
                self.assertEqual(self.call("get", f"/stores/{self.store.id}/schedule/?week={day}").status_code, 400)
                self.assertEqual(self.call("get", f"/dashboard/?date={day}").status_code, 400)
                response = self.call("put", f"/stores/{self.store.id}/schedule/", {**DRAFT, "week_start": day})
                self.assertEqual(response.status_code, 400)

    def test_text_fields_accept_only_text(self):
        for bad in ([1], {"a": 1}, 42, True):
            with self.subTest(name=bad):
                response = self.call("post", f"/stores/{self.store.id}/employees/", {"name": bad})
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Employee.objects.filter(name__in=["[1]", "{'a': 1}", "42", "True"]).exists())

    def test_null_character_that_postgres_cannot_store_is_rejected(self):
        response = self.call(
            "post", "/stores/", {"name": "Lenina\x00", "open_time": "10:00", "close_time": "22:00"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Store.objects.count(), 1)
