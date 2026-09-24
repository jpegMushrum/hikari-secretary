import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.formatting import parse_schedule


class FormattingTests(unittest.TestCase):
    def setUp(self):
        self.tz = ZoneInfo("Europe/Moscow")
        self.now = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)

    def test_full_date_is_converted_to_utc(self):
        result = parse_schedule("23.09.2026 15:30", self.tz, self.now)
        self.assertEqual(result, datetime(2026, 9, 23, 12, 30, tzinfo=timezone.utc))

    def test_short_date_uses_current_year(self):
        result = parse_schedule("23.09 15:30", self.tz, self.now)
        self.assertEqual(result.year, 2026)

    def test_past_time_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_schedule("21.09.2026 15:30", self.tz, self.now)

if __name__ == "__main__":
    unittest.main()
