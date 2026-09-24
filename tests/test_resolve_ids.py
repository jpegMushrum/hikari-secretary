import unittest

from app.resolve_ids import normalize_telegram_reference


class ResolveIdsTests(unittest.TestCase):
    def test_username(self):
        self.assertEqual(normalize_telegram_reference("@example_channel"), "@example_channel")

    def test_public_link(self):
        self.assertEqual(normalize_telegram_reference("https://t.me/example_channel/123"), "@example_channel")

    def test_tg_link(self):
        self.assertEqual(normalize_telegram_reference("tg://resolve?domain=example_channel"), "@example_channel")

    def test_private_invite_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_telegram_reference("https://t.me/+secret-code")

if __name__ == "__main__":
    unittest.main()
