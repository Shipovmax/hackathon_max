import datetime as dt
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.test import override_settings

from apps.core.domain.lifecycle import ensure_instances, mark_done
from apps.core.models import Claim, Completion, ShiftStatus
from apps.core.tests.helpers import make_shift, make_store, make_template, moscow

from .helpers import OwnerApiTestCase

DAY = dt.date(2026, 9, 21)


class DashboardTests(OwnerApiTestCase):
    def setUp(self):
        super().setUp()
        self.opening = make_template(self.store, "Opening", at=(9, 0), tolerance=15)
        self.hall = make_template(self.store, "Hall", at=(10, 0), tolerance=30)
        self.delivery = make_template(self.store, "Delivery", at=(11, 0), claim=True, one_time_on=DAY)
        make_template(self.store, "Closing", at=(22, 0), tolerance=20)

        self.calm = make_store(self.network, "Gagarina, 3")
        make_template(self.calm, "Opening", at=(9, 0))

        for instance in ensure_instances(self.store, DAY):
            if instance.template == self.opening:
                mark_done(instance, self.anna, moscow(9, 40))
            elif instance.template == self.hall:
                mark_done(instance, self.anna, moscow(9, 55))
        calm_instance = ensure_instances(self.calm, DAY)[0]
        mark_done(calm_instance, self.anna, moscow(9, 2))

    def get(self, hour=12, **query):
        with self.at(hour):
            suffix = "&".join(f"{k}={v}" for k, v in query.items())
            return self.call("get", f"/dashboard/?{suffix}" if suffix else "/dashboard/")

    def test_stores_with_problems_come_first_with_counters(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        first, second = response.json()["stores"]
        self.assertEqual(
            (first["name"], first["done"], first["total"], first["health"]),
            ("Lenina, 14", 2, 4, "unclaimed"),
        )
        self.assertEqual((second["name"], second["done"], second["total"], second["health"]), ("Gagarina, 3", 1, 1, "ok"))

    def test_last_event_is_the_latest_completion_time(self):
        first = self.get().json()["stores"][0]
        self.assertEqual(first["last_event_label"], "последнее 09:55")

    def test_store_without_events_has_no_label(self):
        empty = make_store(self.network, "Vostok")
        make_template(empty, "Opening", at=(20, 0))
        store = next(s for s in self.get().json()["stores"] if s["name"] == "Vostok")
        self.assertIsNone(store["last_event_label"])
        self.assertEqual((store["done"], store["total"], store["health"]), (0, 1, "ok"))

    def test_late_completion_counts_as_a_remark(self):
        with self.at(8):
            self.assertEqual(self.call("get", "/dashboard/").json()["stores"][0]["health"], "overdue")

    def test_overdue_task_marks_the_store(self):
        make_template(self.calm, "Hall", at=(10, 0), tolerance=30)
        stores = {s["name"]: s for s in self.get(12).json()["stores"]}
        self.assertEqual(stores["Gagarina, 3"]["health"], "overdue")

    def test_other_owner_sees_none_of_these_stores(self):
        self.other_owner()
        with self.at(12):
            stores = self.call("get", "/dashboard/", user_id=2002).json()["stores"]
        self.assertEqual([s["name"] for s in stores], ["Foreign store"])

    def test_invalid_date_is_a_readable_error(self):
        response = self.get(date="not-a-date")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Дата указана неверно")

    def test_future_day_shows_scheduled_tasks_without_saving_them(self):
        tomorrow = (DAY + dt.timedelta(days=1)).isoformat()
        before = Completion.objects.count(), self.store.task_templates.count()
        stores = {s["name"]: s for s in self.get(date=tomorrow).json()["stores"]}
        self.assertEqual((stores["Lenina, 14"]["done"], stores["Lenina, 14"]["total"]), (0, 3))
        self.assertEqual(before, (Completion.objects.count(), self.store.task_templates.count()))

    def test_unauthenticated_request_is_rejected(self):
        self.assertEqual(self.api.get("/api/dashboard/").status_code, 401)


class StoreDayTests(OwnerApiTestCase):
    def setUp(self):
        super().setUp()
        self.opening = make_template(self.store, "Opening", at=(9, 0), tolerance=15)
        self.delivery = make_template(self.store, "Delivery", at=(14, 0), claim=True, one_time_on=DAY)
        make_shift(self.anna, (9, 0), (17, 0))
        make_shift(self.igor, (14, 0), (22, 0), status=ShiftStatus.DRAFT)
        opening = next(i for i in ensure_instances(self.store, DAY) if i.template == self.opening)
        mark_done(opening, self.anna, moscow(9, 40))

    def day(self, hour=15, date=None):
        with self.at(hour):
            return self.call("get", f"/stores/{self.store.id}/day/" + (f"?date={date}" if date else ""))

    def test_day_card_lists_tasks_in_time_order_with_who_and_when(self):
        body = self.day().json()
        self.assertEqual(body["store"], {"id": self.store.id, "name": "Lenina, 14"})
        opening, delivery = body["tasks"]
        self.assertEqual(
            (opening["title"], opening["status"], opening["late_minutes"], opening["done_by"], opening["done_at"]),
            ("Opening", "done_late", 40, "Anna", "09:40"),
        )
        self.assertEqual((delivery["title"], delivery["status"], delivery["claimed_by"]), ("Delivery", "unclaimed", None))

    def test_only_published_shifts_are_on_shift(self):
        self.assertEqual(
            self.day().json()["on_shift"], [{"name": "Anna", "start": "09:00", "end": "17:00"}]
        )

    def test_claimed_task_names_the_person(self):
        instance = next(i for i in ensure_instances(self.store, DAY) if i.template == self.delivery)
        Claim.objects.create(instance=instance, employee=self.igor)
        delivery = self.day(hour=14).json()["tasks"][1]
        self.assertEqual(delivery["claimed_by"], "Igor")
        self.assertEqual(delivery["status"], "scheduled")

    def test_claimed_task_past_its_tolerance_is_overdue(self):
        instance = next(i for i in ensure_instances(self.store, DAY) if i.template == self.delivery)
        Claim.objects.create(instance=instance, employee=self.igor)
        self.assertEqual(self.day(hour=15).json()["tasks"][1]["status"], "overdue")

    def test_past_day_without_records_is_empty(self):
        yesterday = (DAY - dt.timedelta(days=1)).isoformat()
        self.assertEqual(self.day(date=yesterday).json()["tasks"], [])

    def test_foreign_store_is_not_found(self):
        foreign = self.other_owner()
        with self.at(12):
            response = self.call("get", f"/stores/{foreign.id}/day/")
        self.assertEqual(response.status_code, 404)

    def test_dismissed_history_is_kept_in_the_card(self):
        self.anna.status = "dismissed"
        self.anna.save()
        self.assertEqual(self.day().json()["tasks"][0]["done_by"], "Anna")


class PhotoTests(OwnerApiTestCase):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        make_template(self.store, "Opening", at=(9, 0))
        self.instance = ensure_instances(self.store, DAY)[0]

    def completion(self, photo: bytes | None):
        with override_settings(MEDIA_ROOT=self.media):
            completion = mark_done(self.instance, self.anna, moscow(9, 5))
            if photo:
                completion.photo.save("shot.png", ContentFile(photo))
        return completion

    def test_owner_gets_the_photo_and_the_day_card_links_it(self):
        completion = self.completion(b"\x89PNG-fake-bytes")
        with override_settings(MEDIA_ROOT=self.media), self.at(12):
            card = self.call("get", f"/stores/{self.store.id}/day/").json()["tasks"][0]
            self.assertEqual(card["photo_url"], f"/completions/{completion.id}/photo/")
            response = self.call("get", card["photo_url"])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/png")
            self.assertEqual(b"".join(response.streaming_content), b"\x89PNG-fake-bytes")

    def test_completion_without_photo_has_no_link_and_is_not_found(self):
        completion = self.completion(None)
        with self.at(12):
            card = self.call("get", f"/stores/{self.store.id}/day/").json()["tasks"][0]
            self.assertIsNone(card["photo_url"])
            self.assertEqual(self.call("get", f"/completions/{completion.id}/photo/").status_code, 404)

    def test_another_owner_cannot_open_the_photo(self):
        completion = self.completion(b"secret")
        self.other_owner()
        with override_settings(MEDIA_ROOT=self.media):
            response = self.call("get", f"/completions/{completion.id}/photo/", user_id=2002)
        self.assertEqual(response.status_code, 404)
