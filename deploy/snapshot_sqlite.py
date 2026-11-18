"""One-time SQLite snapshot. Stop the legacy bot before running this step."""
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import shutil
import tempfile


def validate(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise RuntimeError('SQLite snapshot failed integrity validation')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
            raise RuntimeError('SQLite database is empty')


def snapshot(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        validate(destination)
        print('Existing SQLite snapshot retained; no source changes copied')
        return
    if not source.is_file():
        raise FileNotFoundError('Legacy bot.sqlite3 is missing; import is blocked')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.tmp')
    try:
        temporary.unlink(missing_ok=True)
        # The legacy bot must be stopped: copying these files is not an atomic
        # snapshot of a live writer. Never open SQLite on the read-only mount:
        # WAL recovery may need a writable SHM file, even with mode=ro.
        with tempfile.TemporaryDirectory(prefix='hikari-sqlite-') as folder:
            staged = Path(folder) / 'source.sqlite3'
            shutil.copyfile(source, staged)
            for suffix in ('-wal', '-journal'):
                sidecar = Path(str(source) + suffix)
                if sidecar.is_file():
                    shutil.copyfile(sidecar, Path(str(staged) + suffix))
            # SHM is a disposable index: SQLite rebuilds it from the copied WAL.
            # immutable=1 is deliberately not used: it would ignore WAL data.
            with closing(sqlite3.connect(staged)) as old:
                with closing(sqlite3.connect(temporary)) as new:
                    old.backup(new)
                    # The immutable import must not depend on WAL/SHM sidecars.
                    new.execute('PRAGMA journal_mode=DELETE')
        validate(temporary)
        os.chmod(temporary, 0o444)
        os.replace(temporary, destination)
        print('SQLite snapshot created and validated; source unchanged')
    finally:
        if temporary.exists():
            os.chmod(temporary, 0o600)
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    snapshot(sys.argv[1], sys.argv[2])
