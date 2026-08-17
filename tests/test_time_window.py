import unittest
from datetime import UTC, date, datetime

from mevo_transformer import local_day_utc_bounds


class TimeWindowTests(unittest.TestCase):
    def test_summer_day(self):
        self.assertEqual(
            local_day_utc_bounds(date(2026, 8, 16)),
            (
                datetime(2026, 8, 15, 22, tzinfo=UTC),
                datetime(2026, 8, 16, 22, tzinfo=UTC),
            ),
        )

    def test_winter_day(self):
        start, end = local_day_utc_bounds(date(2026, 1, 15))
        self.assertEqual(start.isoformat(), "2026-01-14T23:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-01-15T23:00:00+00:00")

    def test_spring_dst_day_has_23_real_hours(self):
        start, end = local_day_utc_bounds(date(2026, 3, 29))
        self.assertEqual((end - start).total_seconds(), 23 * 60 * 60)

    def test_autumn_dst_day_has_25_real_hours(self):
        start, end = local_day_utc_bounds(date(2026, 10, 25))
        self.assertEqual((end - start).total_seconds(), 25 * 60 * 60)


if __name__ == "__main__":
    unittest.main()
