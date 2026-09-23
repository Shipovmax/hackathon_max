import datetime as dt

from django.test import TestCase

from apps.core.domain.lifecycle import (
    ensure_instances,
    evaluate_status,
    mark_done,
    planned_at,
)
from apps.core.domain.day import day_tasks
from apps.core.models import Claim, Employee, TaskInstance, TaskStatus

from .helpers import make_network, make_store, make_template, moscow

DAY = dt.date(2026, 9, 21)


class LifecycleTests(TestCase):
    def setUp(self):
        self.store = make_store(make_network())
        self.employee = Employee.objects.create(store=self.store, name="Anna")

    def instance(self, template, day=DAY):
        return TaskInstance.objects.select_related("template__store").get(
            template=template, date=day
        ) if TaskInstance.objects.filter(template=template, date=day).exists() else (
            TaskInstance.objects.create(template=template, date=day)
        )

    def test_planned_moment_is_in_the_store_timezone(self):
        instance = self.instance(make_template(self.store, at=(9, 0)))
        self.assertEqual(planned_at(instance), moscow(9, 0))
        self.assertEqual(planned_at(instance).utcoffset(), dt.timedelta(hours=3))

    def test_task_is_scheduled_until_the_tolerance_runs_out(self):
        instance = self.instance(make_template(self.store, at=(9, 0), tolerance=15))
        self.assertEqual(evaluate_status(instance, moscow(8, 0)), TaskStatus.SCHEDULED)
        self.assertEqual(evaluate_status(instance, moscow(9, 10)), TaskStatus.SCHEDULED)

    def test_task_becomes_overdue_after_planned_time_plus_tolerance(self):
        instance = self.instance(make_template(self.store, at=(9, 0), tolerance=15))
        self.assertEqual(evaluate_status(instance, moscow(9, 16)), TaskStatus.OVERDUE)

    def test_unfinished_task_of_a_past_day_is_missed(self):
        instance = self.instance(make_template(self.store, at=(9, 0)))
        self.assertEqual(evaluate_status(instance, moscow(10, 0, DAY + dt.timedelta(days=1))), TaskStatus.MISSED)

    def test_claim_task_nobody_took_is_unclaimed_from_its_planned_time(self):
        instance = self.instance(make_template(self.store, "Delivery", at=(14, 0), claim=True))
        self.assertEqual(evaluate_status(instance, moscow(13, 59)), TaskStatus.SCHEDULED)
        self.assertEqual(evaluate_status(instance, moscow(14, 1)), TaskStatus.UNCLAIMED)

    def test_claimed_task_that_is_not_done_becomes_overdue_not_unclaimed(self):
        instance = self.instance(make_template(self.store, "Delivery", at=(14, 0), tolerance=30, claim=True))
        Claim.objects.create(instance=instance, employee=self.employee)
        instance.refresh_from_db()
        self.assertEqual(evaluate_status(instance, moscow(14, 10)), TaskStatus.SCHEDULED)
        self.assertEqual(evaluate_status(instance, moscow(14, 45)), TaskStatus.OVERDUE)

    def test_mark_done_within_tolerance_is_on_time(self):
        instance = self.instance(make_template(self.store, at=(9, 0), tolerance=15))
        completion = mark_done(instance, self.employee, moscow(9, 10))
        self.assertEqual(completion.late_minutes, 10)
        self.assertEqual(instance.status, TaskStatus.DONE_ON_TIME)
        self.assertEqual(evaluate_status(instance, moscow(23, 0)), TaskStatus.DONE_ON_TIME)

    def test_mark_done_after_tolerance_is_late_by_minutes_from_planned_time(self):
        instance = self.instance(make_template(self.store, at=(9, 0), tolerance=15))
        completion = mark_done(instance, self.employee, moscow(9, 40))
        self.assertEqual(completion.late_minutes, 40)
        self.assertEqual(instance.status, TaskStatus.DONE_LATE)

    def test_mark_done_early_is_not_negative(self):
        instance = self.instance(make_template(self.store, at=(9, 0)))
        self.assertEqual(mark_done(instance, self.employee, moscow(8, 50)).late_minutes, 0)

    def test_mark_done_twice_keeps_the_first_completion(self):
        instance = self.instance(make_template(self.store, at=(9, 0)))
        first = mark_done(instance, self.employee, moscow(9, 5))
        second = mark_done(instance, Employee.objects.create(store=self.store, name="Igor"), moscow(9, 30))
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.employee, self.employee)

    def test_ensure_instances_is_idempotent(self):
        make_template(self.store, "Opening", at=(9, 0))
        make_template(self.store, "Closing", at=(22, 0))
        self.assertEqual(len(ensure_instances(self.store, DAY)), 2)
        self.assertEqual(len(ensure_instances(self.store, DAY)), 2)
        self.assertEqual(TaskInstance.objects.count(), 2)

    def test_ensure_instances_takes_one_time_tasks_only_on_their_date(self):
        make_template(self.store, "Delivery", at=(14, 0), one_time_on=DAY)
        self.assertEqual(len(ensure_instances(self.store, DAY)), 1)
        self.assertEqual(len(ensure_instances(self.store, DAY + dt.timedelta(days=1))), 0)

    def test_deactivated_templates_are_not_scheduled(self):
        template = make_template(self.store, "Old", at=(9, 0))
        template.is_active = False
        template.save()
        self.assertEqual(ensure_instances(self.store, DAY), [])


class StoreDaysOffTests(TestCase):
    """В выходной точка закрыта: ежедневных задач нет, ложных просрочек тоже."""

    def setUp(self):
        self.store = make_store(make_network())
        self.store.closed_weekdays = [DAY.weekday()]
        self.store.save(update_fields=["closed_weekdays"])
        make_template(self.store, "Opening", at=(9, 0))

    def test_daily_tasks_are_not_created_on_a_day_off(self):
        self.assertEqual(ensure_instances(self.store, DAY), [])
        self.assertFalse(TaskInstance.objects.exists())

    def test_daily_tasks_come_back_on_a_working_day(self):
        tomorrow = DAY + dt.timedelta(days=1)
        self.assertEqual([i.template.title for i in ensure_instances(self.store, tomorrow)], ["Opening"])

    def test_one_time_task_on_a_day_off_stays(self):
        """Разовую задачу владелец поставил на эту дату сам — значит, она нужна."""
        make_template(self.store, "Inventory", at=(11, 0), one_time_on=DAY)
        self.assertEqual([i.template.title for i in ensure_instances(self.store, DAY)], ["Inventory"])

    def test_future_day_off_shows_no_daily_tasks(self):
        next_week = DAY + dt.timedelta(days=7)
        rows = day_tasks(self.store, next_week, moscow(12))
        self.assertEqual(rows, [])
