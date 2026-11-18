"""Regression for a read-only source with committed WAL but no SHM."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ReadOnlySnapshotTests(unittest.TestCase):
    def test_readonly_wal_source_without_shm(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'bot.sqlite3'
            subprocess.run([sys.executable, '-c', '''
import os, sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.execute('PRAGMA journal_mode=WAL')
db.execute('CREATE TABLE example(value TEXT)')
db.execute("INSERT INTO example VALUES('committed in WAL')")
db.commit()
os._exit(0)
''', str(source)], check=True)
            Path(str(source) + '-shm').unlink(missing_ok=True)
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(folder).iterdir()}
            self.assertIn('bot.sqlite3-wal', before)
            script = '''
import sqlite3, sys
from contextlib import closing
sys.path.insert(0, '/scripts')
from snapshot_sqlite import snapshot
try:
    with closing(sqlite3.connect('file:/source/bot.sqlite3?mode=ro', uri=True)) as old:
        with closing(sqlite3.connect(':memory:')) as new:
            old.backup(new)
except sqlite3.OperationalError as error:
    assert 'unable to open database file' in str(error), str(error)
else:
    raise AssertionError('Expected original read-only WAL failure')
snapshot('/source/bot.sqlite3', '/output/bot.sqlite3')
with closing(sqlite3.connect('file:/output/bot.sqlite3?immutable=1', uri=True)) as copied:
    assert copied.execute('SELECT * FROM example').fetchall() == [('committed in WAL',)]
snapshot('/source/bot.sqlite3', '/output/bot.sqlite3')
'''
            result = subprocess.run([
                'docker', 'run', '--rm', '--entrypoint', 'python',
                '--mount', f'type=bind,source={folder},target=/source,readonly',
                '--mount', f'type=bind,source={Path(__file__).resolve().parent},target=/scripts,readonly',
                '--tmpfs', '/output', 'python:3.12-slim', '-c', script,
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(folder).iterdir()}
            self.assertEqual(before, after)
