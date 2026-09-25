from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.core.models import Employee, Shift

from .helpers import make_network, make_shift, make_store, moscow


class ShiftNotificationFieldsTests(TestCase):
    def setUp(self):
        store = make_store(make_network())
        self.employee = Employee.objects.create(store=store, name="Igor")

    def test_new_shift_has_no_marks(self):
        shift = make_shift(self.employee)
        self.assertIsNone(shift.start_notified_at)
        self.assertIsNone(shift.summary_sent_at)

    def test_marks_survive_a_reload(self):
        shift = make_shift(self.employee)
        shift.start_notified_at = moscow(9, 0)
        shift.summary_sent_at = moscow(17, 0)
        shift.save(update_fields=["start_notified_at", "summary_sent_at"])

        stored = Shift.objects.get(pk=shift.pk)
        self.assertEqual(stored.start_notified_at, moscow(9, 0))
        self.assertEqual(stored.summary_sent_at, moscow(17, 0))

    def test_unsent_shifts_are_filterable(self):
        sent = make_shift(self.employee)
        sent.start_notified_at = moscow(9, 0)
        sent.save(update_fields=["start_notified_at"])
        pending = make_shift(self.employee, start=(17, 0), end=(22, 0))

        found = Shift.objects.filter(start_notified_at__isnull=True)
        self.assertEqual(list(found), [pending])


class MigrationsTests(TestCase):
    def test_no_missing_migrations(self):
        out = StringIO()
        call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
