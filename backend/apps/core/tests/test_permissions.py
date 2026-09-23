import datetime as dt

from django.test import TestCase

from apps.core.domain.lifecycle import ensure_instances, mark_done
from apps.core.domain.permissions import MarkDenial, check_can_mark, shift_open_until
from apps.core.models import Employee, ShiftStatus

from .helpers import make_network, make_shift, make_store, make_template, moscow

DAY = dt.date(2026, 9, 21)


class CheckCanMarkTests(TestCase):
    def setUp(self):
        network = make_network()
        self.store = make_store(network)
        make_template(self.store, "Opening", at=(9, 0))
        self.instance = ensure_instances(self.store, DAY)[0]
        self.igor = Employee.objects.create(store=self.store, name="Igor")
        make_shift(self.igor, start=(14, 0), end=(22, 0))

    def check(self, employee, hour, minute=0):
        return check_can_mark(employee, self.instance, moscow(hour, minute))

    def test_allowed_while_the_shift_runs(self):
        decision = self.check(self.igor, 15)
        self.assertTrue(decision.allowed)
        self.assertIsNone(decision.denial)

    def test_allowed_within_boundary_tolerance_before_the_shift(self):
        self.assertTrue(self.check(self.igor, 13, 56).allowed)

    def test_allowed_within_boundary_tolerance_after_the_shift(self):
        self.assertTrue(self.check(self.igor, 22, 4).allowed)

    def test_not_started_carries_the_shift_start(self):
        decision = self.check(self.igor, 13, 50)
        self.assertEqual(decision.denial, MarkDenial.NOT_STARTED)
        self.assertEqual(decision.shift_start, dt.time(14, 0))

    def test_ended_carries_the_shift_end(self):
        decision = self.check(self.igor, 22, 10)
        self.assertEqual(decision.denial, MarkDenial.ENDED)
        self.assertEqual(decision.shift_end, dt.time(22, 0))

    def test_day_off_when_there_is_no_shift_today(self):
        anna = Employee.objects.create(store=self.store, name="Anna")
        self.assertEqual(self.check(anna, 15).denial, MarkDenial.DAY_OFF)

    def test_draft_shift_does_not_count(self):
        anna = Employee.objects.create(store=self.store, name="Anna")
        make_shift(anna, start=(9, 0), end=(17, 0), status=ShiftStatus.DRAFT)
        self.assertEqual(self.check(anna, 12).denial, MarkDenial.DAY_OFF)

    def test_shift_of_another_day_does_not_count(self):
        anna = Employee.objects.create(store=self.store, name="Anna")
        make_shift(anna, start=(9, 0), end=(17, 0), day=DAY + dt.timedelta(days=1))
        self.assertEqual(self.check(anna, 12).denial, MarkDenial.DAY_OFF)

    def test_employee_of_another_store_is_denied(self):
        other_store = make_store(make_network(2002), "Gagarina, 3")
        stranger = Employee.objects.create(store=other_store, name="Oleg")
        make_shift(stranger, start=(9, 0), end=(22, 0))
        self.assertEqual(self.check(stranger, 15).denial, MarkDenial.DAY_OFF)

    def test_dismissed_employee_is_denied(self):
        self.igor.status = "dismissed"
        self.igor.save()
        self.assertEqual(self.check(self.igor, 15).denial, MarkDenial.DAY_OFF)

    def test_task_of_another_day_cannot_be_marked(self):
        decision = check_can_mark(self.igor, self.instance, moscow(15, 0, DAY + dt.timedelta(days=1)))
        self.assertEqual(decision.denial, MarkDenial.ENDED)

    def test_already_done_names_who_did_it_and_when(self):
        anna = Employee.objects.create(store=self.store, name="Anna")
        mark_done(self.instance, anna, moscow(9, 3))
        decision = self.check(self.igor, 15)
        self.assertEqual(decision.denial, MarkDenial.ALREADY_DONE)
        self.assertEqual(decision.done_by, "Anna")
        self.assertEqual(decision.done_at, dt.time(9, 3))

    def test_split_shifts_use_the_one_that_is_running(self):
        make_shift(self.igor, start=(9, 0), end=(11, 0))
        self.assertTrue(self.check(self.igor, 10).allowed)
        self.assertTrue(self.check(self.igor, 15).allowed)
        self.assertEqual(self.check(self.igor, 12).denial, MarkDenial.NOT_STARTED)


class TaskWindowTests(TestCase):
    """
    У задачи есть время, раньше которого её не отметить.

    Без него закрытие смены, запланированное на 22:00, закрывалось бы в час дня —
    смена-то идёт.
    """

    def setUp(self):
        network = make_network()
        self.store = make_store(network)
        make_template(self.store, "Closing", at=(22, 0), available_from=(21, 30))
        self.instance = ensure_instances(self.store, DAY)[0]
        self.igor = Employee.objects.create(store=self.store, name="Igor")
        make_shift(self.igor, start=(9, 0), end=(23, 0))

    def check(self, hour, minute=0):
        return check_can_mark(self.igor, self.instance, moscow(hour, minute))

    def test_too_early_during_the_shift_is_refused_with_the_time(self):
        decision = self.check(13)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.denial, MarkDenial.TOO_EARLY)
        self.assertEqual(decision.available_from, dt.time(21, 30))

    def test_allowed_once_the_window_opens(self):
        self.assertFalse(self.check(21, 29).allowed)
        self.assertTrue(self.check(21, 30).allowed)
        self.assertTrue(self.check(22, 30).allowed)

    def test_window_from_midnight_keeps_the_task_open_all_shift(self):
        template = self.instance.template
        template.available_from = dt.time(0, 0)
        template.save(update_fields=["available_from"])
        self.assertTrue(self.check(13).allowed)

    def test_finished_shift_still_wins_over_the_window(self):
        """Порядок отказов важен: сначала смена, потом окно задачи."""
        self.assertEqual(self.check(23, 30).denial, MarkDenial.ENDED)


class ShiftEndTests(TestCase):
    """
    Закрытие в 22:00 при смене до 22:00.

    Магазин закрыли ровно в десять, а подтверждают на пару минут позже — фото закрытой
    двери делают, когда она закрыта. Смена для своей задачи открыта до её срока.
    """

    def setUp(self):
        network = make_network()
        self.store = make_store(network)
        make_template(self.store, "Closing", at=(22, 0), tolerance=20, available_from=(21, 30))
        # Задача следующей смены: её вечерний сотрудник закрывать не должен.
        make_template(self.store, "Night check", at=(22, 10), tolerance=30)
        instances = {i.template.title: i for i in ensure_instances(self.store, DAY)}
        self.closing = instances["Closing"]
        self.night = instances["Night check"]
        self.igor = Employee.objects.create(store=self.store, name="Igor")
        self.shift = make_shift(self.igor, start=(14, 0), end=(22, 0))

    def test_own_task_can_be_confirmed_after_the_shift_ends(self):
        self.assertTrue(check_can_mark(self.igor, self.closing, moscow(22, 3)).allowed)
        self.assertTrue(check_can_mark(self.igor, self.closing, moscow(22, 19)).allowed)

    def test_after_the_task_deadline_the_shift_is_over(self):
        decision = check_can_mark(self.igor, self.closing, moscow(22, 21))
        self.assertEqual(decision.denial, MarkDenial.ENDED)

    def test_task_of_the_next_shift_is_not_extended(self):
        decision = check_can_mark(self.igor, self.night, moscow(22, 8))
        self.assertEqual(decision.denial, MarkDenial.ENDED)

    def test_shift_stays_open_until_its_last_task_deadline(self):
        self.assertEqual(shift_open_until(self.shift), moscow(22, 20))

    def test_shift_without_late_tasks_closes_at_the_boundary(self):
        early = make_shift(Employee.objects.create(store=self.store, name="Anna"), start=(9, 0), end=(14, 0))
        self.assertEqual(shift_open_until(early), moscow(14, 5))
