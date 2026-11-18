import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from snapshot_sqlite import snapshot


class SnapshotTests(unittest.TestCase):
    def test_snapshot_includes_wal_and_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'source.db', Path(folder) / 'snapshot.db'
            db = sqlite3.connect(source)
            try:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE example(value TEXT)')
                db.execute("INSERT INTO example VALUES('before cutover')")
                db.commit()
                snapshot(source, target)
                self.assertFalse(Path(str(target) + '-wal').exists())
                db.execute("INSERT INTO example VALUES('after cutover')")
                db.commit()
                snapshot(source, target)
                with closing(sqlite3.connect(target)) as copied:
                    self.assertEqual(copied.execute('SELECT * FROM example').fetchall(), [('before cutover',)])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM example').fetchone(), (2,))
            finally:
                db.close()
                if target.exists():
                    os.chmod(target, 0o600)

    def test_missing_source_does_not_create_empty_database(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'snapshot.db'
            with self.assertRaises(FileNotFoundError):
                snapshot(Path(folder) / 'missing.db', target)
            self.assertFalse(target.exists())

    def test_corrupt_snapshot_blocks_restart_instead_of_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'snapshot.db'
            target.write_bytes(b'not sqlite')
            with self.assertRaises(sqlite3.DatabaseError):
                snapshot(Path(folder) / 'source.db', target)
            self.assertEqual(target.read_bytes(), b'not sqlite')
