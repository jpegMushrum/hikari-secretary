import os
from pathlib import Path
import stat
import tempfile
import unittest

from pin_images import pin_images


class PinImagesTests(unittest.TestCase):
    def test_repeated_releases_preserve_server_settings_and_file_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            original = b'# settings\r\nPORT=880\r\nTEXT="first\r\nsecond"'
            path.write_bytes(original)
            path.chmod(0o600)
            pin_images(path, "backend1", "bot1", "miniapp1")
            with path.open("ab") as env:
                env.write(b"EXTRA=on\r\n")
            pin_images(path, "backend2", "bot2", "miniapp2")
            content = path.read_bytes()
            self.assertTrue(content.startswith(original + b"\r\nEXTRA=on\r\n"))
            self.assertTrue(content.endswith(b"BACKEND_IMAGE=backend2\r\nBOT_IMAGE=bot2\r\nMINIAPP_IMAGE=miniapp2\r\n"))
            self.assertNotIn(b"backend1", content)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            pin_images(path, "backend2", "bot2", "miniapp2")
            self.assertEqual(path.read_bytes(), content)

    def test_damaged_managed_block_leaves_env_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            original = b"# Managed by deploy/production-release.sh\nEXTRA=manual-edit\n"
            path.write_bytes(original)
            with self.assertRaises(ValueError):
                pin_images(path, "backend", "bot", "miniapp")
            self.assertEqual(path.read_bytes(), original)
