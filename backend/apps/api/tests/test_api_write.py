import datetime as dt

from apps.core.models import (
    Completion,
    Employee,
    InviteCode,
    MaxAccount,
    Shift,
    ShiftStatus,
    Store,
    TaskInstance,
    TaskTemplate,
)

from apps.core.tests.helpers import moscow

from .helpers import OwnerApiTestCase

MONDAY = dt.date(2026, 9, 21)


def shift(employee, offset, start="09:00", end="17:00", week=MONDAY):
    return {
        "employee_id": employee.id,
        "date": (week + dt.timedelta(days=offset)).isoformat(),
        "start": start,
        "end": end,
    }


class StoreTests(OwnerApiTestCase):
    def test_list_shows_stores_with_people_and_invite_codes(self):
        InviteCode.issue(self.anna)
        body = self.call("get", "/stores/").json()
        self.assertEqual(len(body), 1)
        people = {p["name"]: p for p in body[0]["employees"]}
        self.assertEqual(people["Anna"]["status"], "invited")
        self.assertEqual(len(people["Anna"]["invite_code"]), 8)
        self.assertIsNone(people["Igor"]["invite_code"])
        self.assertEqual((body[0]["open_time"], body[0]["close_time"]), ("09:00", "22:00"))

    def test_create_store(self):
        response = self.call(
            "post", "/stores/", {"name": " Vostok ", "address": "Mira, 1", "open_time": "10:00", "close_time": "21:00"}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "Vostok")
        self.assertEqual(response.json()["employees"], [])
        self.assertTrue(Store.objects.filter(name="Vostok", network=self.network).exists())

    def test_store_must_close_after_it_opens(self):
        response = self.call(
            "post", "/stores/", {"name": "X", "address": "", "open_time": "22:00", "close_time": "09:00"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("позже", response.json()["detail"])

    def test_store_needs_a_name_and_valid_times(self):
        base = {"address": "", "open_time": "09:00", "close_time": "21:00"}
        self.assertEqual(self.call("post", "/stores/", {**base, "name": "  "}).status_code, 400)
        self.assertEqual(self.call("post", "/stores/", {**base, "name": "X", "open_time": "9am"}).status_code, 400)

    def test_dismissed_employees_are_listed_last(self):
        self.anna.status = "dismissed"
        self.anna.save()
        names = [p["name"] for p in self.call("get", "/stores/").json()[0]["employees"]]
        self.assertEqual(names, ["Igor", "Anna"])


class EmployeeTests(OwnerApiTestCase):
    def test_new_employee_gets_a_one_time_code(self):
        response = self.call("post", f"/stores/{self.store.id}/employees/", {"name": "Dasha"})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["name"], body["status"]), ("Dasha", "invited"))
        self.assertTrue(InviteCode.objects.filter(code=body["invite_code"], used_at__isnull=True).exists())

    def test_employee_needs_a_name(self):
        response = self.call("post", f"/stores/{self.store.id}/employees/", {"name": ""})
        self.assertEqual(response.status_code, 400)

    def test_new_invite_replaces_the_old_code(self):
        old = InviteCode.issue(self.anna).code
        new = self.call("post", f"/employees/{self.anna.id}/invite/").json()["invite_code"]
        self.assertNotEqual(old, new)
        self.assertFalse(InviteCode.objects.filter(code=old).exists())
        self.assertEqual(InviteCode.objects.filter(employee=self.anna, used_at__isnull=True).count(), 1)

    def test_connected_employee_shows_as_connected_and_cannot_be_reinvited(self):
        self.anna.account = MaxAccount.objects.create(max_user_id=555)
        self.anna.save()
        listed = {p["name"]: p for p in self.call("get", "/stores/").json()[0]["employees"]}
        self.assertEqual(listed["Anna"]["status"], "connected")
        self.assertEqual(self.call("post", f"/employees/{self.anna.id}/invite/").status_code, 409)

    def test_dismissal_keeps_the_record_and_kills_the_code(self):
        InviteCode.issue(self.anna)
        response = self.call("post", f"/employees/{self.anna.id}/dismiss/")
        self.assertEqual(response.json()["status"], "dismissed")
        self.assertIsNone(response.json()["invite_code"])
        self.assertTrue(Employee.objects.filter(pk=self.anna.id).exists())
        self.assertEqual(InviteCode.objects.filter(employee=self.anna).count(), 0)
        self.assertEqual(self.call("post", f"/employees/{self.anna.id}/invite/").status_code, 409)

    def test_foreign_employee_is_not_reachable(self):
        foreign = Employee.objects.create(store=self.other_owner(), name="Oleg")
        self.assertEqual(self.call("post", f"/employees/{foreign.id}/dismiss/").status_code, 404)
        self.assertEqual(self.call("post", f"/employees/{foreign.id}/invite/").status_code, 404)
        self.assertEqual(self.call("delete", f"/employees/{foreign.id}/").status_code, 404)


class EmployeeRemovalTests(OwnerApiTestCase):
    """Убрать уволенного из списка, не потеряв историю его отметок."""

    def names(self):
        return [p["name"] for p in self.call("get", "/stores/").json()[0]["employees"]]

    def dismiss(self, employee):
        self.assertEqual(self.call("post", f"/employees/{employee.id}/dismiss/").status_code, 200)

    def test_employee_who_never_worked_is_deleted_outright(self):
        InviteCode.issue(self.anna)
        self.dismiss(self.anna)

        response = self.call("delete", f"/employees/{self.anna.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Employee.objects.filter(pk=self.anna.id).exists())
        self.assertEqual(InviteCode.objects.filter(employee_id=self.anna.id).count(), 0)
        self.assertEqual(self.names(), ["Igor"])

    def test_employee_with_history_disappears_from_the_list_but_keeps_it(self):
        template = TaskTemplate.objects.create(
            store=self.store, title="Opening", planned_time=dt.time(9), available_from=dt.time(9)
        )
        instance = TaskInstance.objects.create(template=template, date=MONDAY)
        completion = Completion.objects.create(
            instance=instance, employee=self.anna, completed_at=moscow(9, 3, MONDAY)
        )
        self.dismiss(self.anna)

        response = self.call("delete", f"/employees/{self.anna.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.names(), ["Igor"])
        # Запись и отметка целы: в карточке дня видно, кто закрыл задачу.
        self.anna.refresh_from_db()
        self.assertEqual(self.anna.status, "removed")
        completion.refresh_from_db()
        self.assertEqual(completion.employee_id, self.anna.id)

    def test_employee_with_shifts_is_kept_too(self):
        Shift.objects.create(
            employee=self.anna,
            store=self.store,
            date=MONDAY,
            start_time=dt.time(9),
            end_time=dt.time(17),
            status=ShiftStatus.PUBLISHED,
        )
        self.dismiss(self.anna)

        self.assertEqual(self.call("delete", f"/employees/{self.anna.id}/").status_code, 204)

        self.anna.refresh_from_db()
        self.assertEqual(self.anna.status, "removed")
        self.assertEqual(Shift.objects.filter(employee=self.anna).count(), 1)

    def test_working_employee_cannot_be_removed(self):
        response = self.call("delete", f"/employees/{self.anna.id}/")

        self.assertEqual(response.status_code, 409)
        self.assertIn("уволен", response.json()["detail"])
        self.assertEqual(self.names(), ["Anna", "Igor"])

    def test_removing_twice_is_harmless(self):
        Shift.objects.create(
            employee=self.anna,
            store=self.store,
            date=MONDAY,
            start_time=dt.time(9),
            end_time=dt.time(17),
            status=ShiftStatus.PUBLISHED,
        )
        self.dismiss(self.anna)

        self.assertEqual(self.call("delete", f"/employees/{self.anna.id}/").status_code, 204)
        self.assertEqual(self.call("delete", f"/employees/{self.anna.id}/").status_code, 204)

        self.assertEqual(self.names(), ["Igor"])


class TaskTemplateTests(OwnerApiTestCase):
    def path(self):
        return f"/stores/{self.store.id}/task-templates/"

    def test_create_daily_task_with_defaults(self):
        response = self.call("post", self.path(), {"title": "Opening", "planned_time": "09:00"})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["kind"], body["tolerance_minutes"], body["requires_photo"]), ("daily", 15, True))
        self.assertFalse(body["requires_claim"])
        self.assertIsNone(body["on_date"])

    def test_completion_window_defaults_to_half_an_hour_before_the_plan(self):
        body = self.call("post", self.path(), {"title": "Closing", "planned_time": "22:00"}).json()
        self.assertEqual(body["available_from"], "21:30")

    def test_completion_window_is_kept_as_given(self):
        payload = {"title": "Closing", "planned_time": "22:00", "available_from": "20:00"}
        body = self.call("post", self.path(), payload).json()
        self.assertEqual(body["available_from"], "20:00")

    def test_completion_window_cannot_start_after_the_plan(self):
        payload = {"title": "Closing", "planned_time": "22:00", "available_from": "22:30"}
        self.assertEqual(self.call("post", self.path(), payload).status_code, 400)

    def test_early_plan_clamps_the_window_to_midnight(self):
        body = self.call("post", self.path(), {"title": "Night", "planned_time": "00:10"}).json()
        self.assertEqual(body["available_from"], "00:00")

    def test_one_time_task_needs_a_date(self):
        payload = {"title": "Delivery", "planned_time": "14:00", "kind": "one_time"}
        self.assertEqual(self.call("post", self.path(), payload).status_code, 400)
        ok = self.call("post", self.path(), {**payload, "on_date": "2026-09-25", "requires_claim": True})
        self.assertEqual((ok.status_code, ok.json()["on_date"], ok.json()["requires_claim"]), (201, "2026-09-25", True))

    def test_daily_task_drops_a_stray_date(self):
        response = self.call("post", self.path(), {"title": "Opening", "planned_time": "09:00", "on_date": "2026-09-25"})
        self.assertIsNone(response.json()["on_date"])

    def test_validation_messages(self):
        base = {"title": "Opening", "planned_time": "09:00"}
        self.assertEqual(self.call("post", self.path(), {**base, "title": " "}).status_code, 400)
        self.assertEqual(self.call("post", self.path(), {**base, "planned_time": "late"}).status_code, 400)
        self.assertEqual(self.call("post", self.path(), {**base, "tolerance_minutes": 999}).status_code, 400)
        self.assertEqual(self.call("post", self.path(), {**base, "tolerance_minutes": "15"}).status_code, 400)
        self.assertEqual(self.call("post", self.path(), {**base, "kind": "weekly"}).status_code, 400)
        self.assertEqual(self.call("post", self.path(), {**base, "requires_photo": "yes"}).status_code, 400)

    def test_list_is_ordered_by_time(self):
        self.call("post", self.path(), {"title": "Closing", "planned_time": "22:00"})
        self.call("post", self.path(), {"title": "Opening", "planned_time": "09:00"})
        titles = [t["title"] for t in self.call("get", self.path()).json()]
        self.assertEqual(titles, ["Opening", "Closing"])

    def test_patch_changes_only_the_given_fields(self):
        created = self.call("post", self.path(), {"title": "Opening", "planned_time": "09:00"}).json()
        response = self.call("patch", f"/task-templates/{created['id']}/", {"planned_time": "09:30", "requires_photo": False})
        body = response.json()
        self.assertEqual((body["title"], body["planned_time"], body["requires_photo"]), ("Opening", "09:30", False))
        self.assertEqual(body["tolerance_minutes"], 15)

    def test_patch_can_turn_a_daily_task_into_a_one_time_one(self):
        created = self.call("post", self.path(), {"title": "Inventory", "planned_time": "10:00"}).json()
        url = f"/task-templates/{created['id']}/"
        self.assertEqual(self.call("patch", url, {"kind": "one_time"}).status_code, 400)
        ok = self.call("patch", url, {"kind": "one_time", "on_date": "2026-09-30"})
        self.assertEqual((ok.status_code, ok.json()["on_date"]), (200, "2026-09-30"))

    def test_delete_hides_the_task_but_keeps_the_row(self):
        created = self.call("post", self.path(), {"title": "Opening", "planned_time": "09:00"}).json()
        response = self.call("delete", f"/task-templates/{created['id']}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.call("get", self.path()).json(), [])
        self.assertFalse(TaskTemplate.objects.get(pk=created["id"]).is_active)
        self.assertEqual(self.call("delete", f"/task-templates/{created['id']}/").status_code, 404)

    def test_every_change_moves_updated_at_for_the_shift_board(self):
        """
        По `updated_at` планировщик рассылает смене обновлённый список задач.

        Отдельная проверка нужна из-за `save(update_fields=...)`: Django не трогает
        поля с `auto_now`, если их не перечислить, и удаление задачи прошло бы тихо.
        """
        created = self.call("post", self.path(), {"title": "Opening", "planned_time": "09:00"}).json()
        template = TaskTemplate.objects.get(pk=created["id"])
        after_create = template.updated_at

        self.call("patch", f"/task-templates/{created['id']}/", {"planned_time": "09:30"})
        template.refresh_from_db()
        after_patch = template.updated_at
        self.assertGreater(after_patch, after_create)

        self.call("delete", f"/task-templates/{created['id']}/")
        template.refresh_from_db()
        self.assertGreater(template.updated_at, after_patch)

    def test_foreign_task_is_not_reachable(self):
        foreign = self.other_owner()
        template = TaskTemplate.objects.create(store=foreign, title="X", planned_time=dt.time(9))
        self.assertEqual(self.call("patch", f"/task-templates/{template.id}/", {"title": "Y"}).status_code, 404)
        self.assertEqual(self.call("get", f"/stores/{foreign.id}/task-templates/").status_code, 404)


class ScheduleTests(OwnerApiTestCase):
    def url(self, suffix=""):
        return f"/stores/{self.store.id}/schedule/{suffix}"

    def draft(self, shifts, week=MONDAY):
        return {"week_start": week.isoformat(), "shifts": shifts}

    def test_empty_week_is_a_draft_with_the_whole_week_uncovered(self):
        body = self.call("get", self.url(f"?week={MONDAY}")).json()
        self.assertEqual((body["status"], body["shifts"]), ("draft", []))
        self.assertEqual(len(body["gaps"]), 7)
        self.assertEqual({e["name"] for e in body["employees"]}, {"Anna", "Igor"})
        self.assertEqual((body["open_time"], body["close_time"]), ("09:00", "22:00"))

    def test_week_is_normalised_to_its_monday(self):
        wednesday = MONDAY + dt.timedelta(days=2)
        self.assertEqual(self.call("get", self.url(f"?week={wednesday}")).json()["week_start"], MONDAY.isoformat())

    def test_saving_a_draft_keeps_it_unpublished_and_reports_gaps(self):
        shifts = [shift(self.anna, d, "09:00", "17:00") for d in range(7)] + [shift(self.igor, d, "17:00", "22:00") for d in range(6)]
        body = self.call("put", self.url(), self.draft(shifts)).json()
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["gaps"], [{"date": (MONDAY + dt.timedelta(days=6)).isoformat(), "start": "17:00", "end": "22:00"}])
        self.assertEqual(Shift.objects.filter(store=self.store, status=ShiftStatus.DRAFT).count(), 13)

    def test_saving_replaces_the_week_and_leaves_other_weeks_alone(self):
        next_week = MONDAY + dt.timedelta(days=7)
        self.call("put", self.url(), self.draft([shift(self.anna, 0, week=next_week)], week=next_week))
        self.call("put", self.url(), self.draft([shift(self.anna, 0), shift(self.anna, 1)]))
        self.call("put", self.url(), self.draft([shift(self.igor, 3)]))
        this_week = self.call("get", self.url(f"?week={MONDAY}")).json()["shifts"]
        self.assertEqual([s["employee_id"] for s in this_week], [self.igor.id])
        self.assertEqual(len(self.call("get", self.url(f"?week={next_week}")).json()["shifts"]), 1)

    def test_coverage_check_does_not_save_anything(self):
        response = self.call("post", self.url("coverage/"), self.draft([shift(self.anna, 0, "09:00", "14:00")]))
        self.assertEqual(response.status_code, 200)
        first_day = [g for g in response.json()["gaps"] if g["date"] == MONDAY.isoformat()]
        self.assertEqual(first_day, [{"date": MONDAY.isoformat(), "start": "14:00", "end": "22:00"}])
        self.assertEqual(Shift.objects.count(), 0)

    def test_coverage_tolerates_five_minutes_at_the_edges(self):
        response = self.call("post", self.url("coverage/"), self.draft([shift(self.anna, 0, "09:00", "21:55")]))
        self.assertEqual([g for g in response.json()["gaps"] if g["date"] == MONDAY.isoformat()], [])

    def test_publishing_makes_the_week_published(self):
        body = self.call("post", self.url("publish/"), self.draft([shift(self.anna, 0)])).json()
        self.assertEqual(body["status"], "published")
        self.assertEqual(Shift.objects.filter(status=ShiftStatus.PUBLISHED).count(), 1)

    def test_editing_a_published_week_keeps_it_published(self):
        self.call("post", self.url("publish/"), self.draft([shift(self.anna, 0)]))
        body = self.call("put", self.url(), self.draft([shift(self.anna, 0), shift(self.igor, 1)])).json()
        self.assertEqual(body["status"], "published")
        self.assertEqual(Shift.objects.filter(status=ShiftStatus.DRAFT).count(), 0)
        self.assertEqual(Shift.objects.count(), 2)

    def test_empty_week_cannot_be_published(self):
        response = self.call("post", self.url("publish/"), self.draft([]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("смену", response.json()["detail"])

    def test_shift_must_end_after_it_starts(self):
        response = self.call("put", self.url(), self.draft([shift(self.anna, 0, "17:00", "09:00")]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Anna", response.json()["detail"])

    def test_overlapping_shifts_of_one_person_are_rejected(self):
        response = self.call("put", self.url(), self.draft([shift(self.anna, 0, "09:00", "15:00"), shift(self.anna, 0, "14:00", "20:00")]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("пересекаются", response.json()["detail"])

    def test_two_different_people_may_overlap(self):
        response = self.call("put", self.url(), self.draft([shift(self.anna, 0, "09:00", "17:00"), shift(self.igor, 0, "14:00", "22:00")]))
        self.assertEqual(response.status_code, 200)

    def test_shift_outside_the_week_is_rejected(self):
        response = self.call("put", self.url(), self.draft([shift(self.anna, 8)]))
        self.assertEqual(response.status_code, 400)

    def test_employee_of_another_store_or_a_dismissed_one_is_rejected(self):
        stranger = Employee.objects.create(store=self.other_owner(), name="Oleg")
        self.assertEqual(self.call("put", self.url(), self.draft([shift(stranger, 0)])).status_code, 400)
        self.igor.status = "dismissed"
        self.igor.save()
        self.assertEqual(self.call("put", self.url(), self.draft([shift(self.igor, 0)])).status_code, 400)

    def test_malformed_body_is_a_clean_400(self):
        self.assertEqual(self.call("put", self.url(), {"week_start": MONDAY.isoformat()}).status_code, 400)
        self.assertEqual(self.call("put", self.url(), {"shifts": []}).status_code, 400)
        self.assertEqual(self.call("put", self.url(), self.draft(["nope"])).status_code, 400)

    def test_foreign_store_schedule_is_not_reachable(self):
        foreign = self.other_owner()
        self.assertEqual(self.call("get", f"/stores/{foreign.id}/schedule/").status_code, 404)
        self.assertEqual(self.call("put", f"/stores/{foreign.id}/schedule/", self.draft([])).status_code, 404)


class StoreEditTests(OwnerApiTestCase):
    """Точку правят после создания: часы работы и выходные меняются со временем."""

    def url(self):
        return f"/stores/{self.store.id}/"

    def test_hours_can_be_changed_after_creation(self):
        response = self.call("patch", self.url(), {"open_time": "10:00", "close_time": "21:00"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["open_time"], response.json()["close_time"]), ("10:00", "21:00"))
        self.store.refresh_from_db()
        self.assertEqual(self.store.open_time, dt.time(10))

    def test_untouched_fields_keep_their_values(self):
        body = self.call("patch", self.url(), {"name": "Lenina, 14A"}).json()
        self.assertEqual((body["name"], body["open_time"], body["close_time"]), ("Lenina, 14A", "09:00", "22:00"))

    def test_new_opening_is_checked_against_the_current_closing(self):
        response = self.call("patch", self.url(), {"open_time": "23:00"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("позже", response.json()["detail"])

    def test_days_off_are_saved_sorted_and_without_repeats(self):
        body = self.call("patch", self.url(), {"closed_weekdays": [6, 5, 6]}).json()
        self.assertEqual(body["closed_weekdays"], [5, 6])

    def test_days_off_are_validated(self):
        for bad in ([7], [-1], ["sun"], [True], "6", list(range(7))):
            with self.subTest(bad=bad):
                self.assertEqual(self.call("patch", self.url(), {"closed_weekdays": bad}).status_code, 400)

    def test_new_store_can_be_created_with_days_off(self):
        payload = {"name": "Vostok", "address": "", "open_time": "10:00", "close_time": "20:00", "closed_weekdays": [0]}
        body = self.call("post", "/stores/", payload).json()
        self.assertEqual(body["closed_weekdays"], [0])

    def test_list_reports_days_off(self):
        self.call("patch", self.url(), {"closed_weekdays": [6]})
        self.assertEqual(self.call("get", "/stores/").json()[0]["closed_weekdays"], [6])

    def test_foreign_store_cannot_be_edited(self):
        foreign = self.other_owner()
        self.assertEqual(self.call("patch", f"/stores/{foreign.id}/", {"name": "Mine"}).status_code, 404)


class ScheduleDaysOffTests(OwnerApiTestCase):
    """Пустой выходной в графике — это не окно, и красным его не подсвечиваем."""

    def test_day_off_is_not_reported_as_a_gap(self):
        sunday = MONDAY + dt.timedelta(days=6)
        self.call("patch", f"/stores/{self.store.id}/", {"closed_weekdays": [6]})
        body = self.call("get", f"/stores/{self.store.id}/schedule/?week={MONDAY}").json()
        self.assertEqual(body["closed_weekdays"], [6])
        self.assertEqual(len(body["gaps"]), 6)
        self.assertNotIn(sunday.isoformat(), {g["date"] for g in body["gaps"]})

    def test_coverage_check_skips_days_off_too(self):
        self.call("patch", f"/stores/{self.store.id}/", {"closed_weekdays": [5, 6]})
        draft = {"week_start": MONDAY.isoformat(), "shifts": [shift(self.anna, d, "09:00", "22:00") for d in range(5)]}
        response = self.call("post", f"/stores/{self.store.id}/schedule/coverage/", draft)
        self.assertEqual(response.json()["gaps"], [])
