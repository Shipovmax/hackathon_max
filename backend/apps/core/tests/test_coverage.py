from datetime import time

from django.test import SimpleTestCase

from apps.core.domain.coverage import find_gaps

OPEN, CLOSE = time(9), time(22)


def gaps(shifts, tolerance=5):
    return find_gaps(OPEN, CLOSE, shifts, tolerance)


class FindGapsTests(SimpleTestCase):
    def test_full_coverage_by_two_shifts(self):
        self.assertEqual(gaps([(time(9), time(17)), (time(17), time(22))]), [])

    def test_gap_in_the_middle(self):
        self.assertEqual(
            gaps([(time(9), time(14)), (time(17), time(22))]), [(time(14), time(17))]
        )

    def test_gap_at_the_end_of_the_day(self):
        self.assertEqual(gaps([(time(9), time(17))]), [(time(17), time(22))])

    def test_gap_at_the_start_of_the_day(self):
        self.assertEqual(gaps([(time(12), time(22))]), [(time(9), time(12))])

    def test_no_shifts_means_the_whole_day_is_open(self):
        self.assertEqual(gaps([]), [(time(9), time(22))])

    def test_shift_ending_five_minutes_early_still_covers_closing(self):
        self.assertEqual(gaps([(time(9), time(21, 55))]), [])

    def test_shift_starting_five_minutes_late_still_covers_opening(self):
        self.assertEqual(gaps([(time(9, 5), time(22))]), [])

    def test_ten_minutes_short_is_a_gap(self):
        self.assertEqual(gaps([(time(9), time(21, 50))]), [(time(21, 50), time(22))])

    def test_overlapping_shifts_are_merged(self):
        self.assertEqual(gaps([(time(9), time(15)), (time(13), time(22))]), [])

    def test_tiny_break_between_shifts_is_bridged(self):
        self.assertEqual(gaps([(time(9), time(15)), (time(15, 4), time(22))]), [])

    def test_break_longer_than_tolerance_is_reported(self):
        self.assertEqual(
            gaps([(time(9), time(15)), (time(15, 6), time(22))]), [(time(15), time(15, 6))]
        )

    def test_shift_after_closing_does_not_cover_the_day(self):
        self.assertEqual(gaps([(time(23), time(23, 30))]), [(time(9), time(22))])

    def test_unsorted_input_gives_the_same_result(self):
        self.assertEqual(
            gaps([(time(17), time(22)), (time(9), time(14))]), [(time(14), time(17))]
        )
