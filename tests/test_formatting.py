import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.formatting import formatting_loss, parse_schedule, render_vk_text


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

    def test_style_warns_but_url_does_not(self):
        self.assertTrue(formatting_loss([{"type": "bold"}]))
        self.assertFalse(formatting_loss([{"type": "url"}]))

    def test_named_link_is_preserved_for_vk(self):
        text = "Смотрите сайт 🚀 здесь"
        # Telegram counts the rocket as two UTF-16 units.
        entities = [{"type": "text_link", "offset": 17, "length": 5, "url": "https://example.com"}]
        self.assertEqual(render_vk_text(text, entities), "Смотрите сайт 🚀 здесь (https://example.com)")


if __name__ == "__main__":
    unittest.main()
