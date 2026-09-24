import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram.types import RichMessage

from app.formatting import (
    parse_schedule,
    rich_message_from_json,
    rich_message_preview,
    rich_message_to_json,
)


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

    def test_rich_message_round_trip_and_preview(self):
        incoming = RichMessage.model_validate(
            {
                "blocks": [
                    {
                        "type": "heading",
                        "text": {"type": "bold", "text": "Лекция"},
                        "size": 2,
                    },
                    {"type": "paragraph", "text": "こんにちは"},
                    {"type": "divider"},
                    {"type": "footer", "text": "26 сентября, 16:30"},
                ]
            }
        )
        stored = rich_message_to_json(incoming)
        outgoing = rich_message_from_json(stored)

        self.assertEqual(len(outgoing.blocks), 4)
        self.assertEqual(outgoing.blocks[0].type, "heading")
        self.assertEqual(
            rich_message_preview(stored),
            "Лекция\nこんにちは\n26 сентября, 16:30",
        )

    def test_registration_button_is_added_to_rich_message(self):
        url = "https://t.me/example_bot?start=event_2"
        outgoing = rich_message_from_json(
            {"blocks": [{"type": "paragraph", "text": "Мероприятие"}]},
            url,
        )

        button_block = outgoing.blocks[-1]
        self.assertEqual(button_block.type, "buttons")
        self.assertEqual(button_block.buttons[0].url, url)
        self.assertEqual(button_block.buttons[0].style, "primary")
        self.assertIsNone(button_block.align)

if __name__ == "__main__":
    unittest.main()
