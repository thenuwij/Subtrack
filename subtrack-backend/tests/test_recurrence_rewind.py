import unittest
from datetime import datetime

from app.services.recurrence import occurrences_between, rewind_anchor


class RewindAnchorTests(unittest.TestCase):
    def test_weekly_rent_counts_every_charge_in_the_month(self):
        # Next rent is 9 Nov; 2 Nov was already paid but is still November's cost.
        anchor = rewind_anchor(datetime(2026, 11, 9), "week", datetime(2026, 11, 1), 1)
        dates = occurrences_between(anchor, "week", datetime(2026, 11, 1), datetime(2026, 11, 30, 23, 59), interval_count=1)
        self.assertEqual([d.day for d in dates], [2, 9, 16, 23, 30])

    def test_month_end_anchor_rewinds_to_month_end(self):
        anchor = rewind_anchor(datetime(2026, 3, 31), "month", datetime(2026, 2, 28), 1)
        self.assertEqual(anchor, datetime(2026, 2, 28))

    def test_anchor_already_before_start_is_unchanged(self):
        self.assertEqual(rewind_anchor(datetime(2026, 1, 5), "week", datetime(2026, 2, 1), 2), datetime(2026, 1, 5))

    def test_yearly_payment_only_counts_in_its_month(self):
        anchor = rewind_anchor(datetime(2027, 3, 10), "year", datetime(2026, 11, 1), 1)
        self.assertEqual(occurrences_between(anchor, "year", datetime(2026, 11, 1), datetime(2026, 11, 30), interval_count=1), [])


if __name__ == "__main__":
    unittest.main()


class RewindKeepsDayTests(unittest.TestCase):
    def test_rewind_past_a_short_month_keeps_the_30th(self):
        from app.services.recurrence import occurrences_between, rewind_anchor
        due = datetime(2026, 10, 30)
        for start in (datetime(2026, 8, 1), datetime(2024, 11, 1)):
            anchor = rewind_anchor(due, "monthly", start)
            dates = occurrences_between(anchor, "monthly", start, datetime(2026, 10, 31))
            self.assertEqual(dates[-1], due)
