"""Exercise the Linux backup worker without a running production stack or bucket."""
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().with_name("archive-backup.sh")
UUID = "11111111-1111-4111-8111-111111111111"


@unittest.skipUnless(sys.platform.startswith("linux"), "The backup host runs Linux")
class ArchiveBackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.backups = self.root / "bucket/club/backups"
        self.backups.mkdir(parents=True)
        self.work = self.root / "tmp"
        self.work.mkdir()
        self.command("date", '#!/bin/sh\necho 20261120T120000Z\n')
        self.command("docker", """#!/bin/sh
case "$*" in
    *pg_dump*) printf test-dump ;;
    *pg_restore*) grep -q test-dump ;;
    *' sh bot') [ -f "$FIXTURE/photo.jpg" ] || exit 42; tar -C "$FIXTURE" -cf - photo.jpg ;;
    *' sh backend') exit 42 ;;
    *) exit 1 ;;
esac
""")
        (self.root / "photo.jpg").write_bytes(b"test-image")
        self.command("aws", """#!/usr/bin/env python3
import json, os, shutil, sys
from pathlib import Path
root = Path(os.environ['FIXTURE']) / 'bucket'
def object_path(uri):
    assert uri.startswith('s3://example/'), uri
    return root / uri.removeprefix('s3://example/')

args = sys.argv[1:]
if args[:2] == ['s3', 'cp']:
    src, dst = args[2:4]
    source = object_path(src) if src.startswith('s3:') else Path(src)
    if dst == '-':
        sys.stdout.buffer.write(b'damaged' if os.environ.get('CORRUPT') else source.read_bytes())
    else:
        target = object_path(dst)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
elif args[:2] == ['s3', 'rm']:
    object_path(args[2]).unlink(missing_ok=True)
elif args[:2] == ['s3api', 'list-objects-v2']:
    assert args[args.index('--prefix')+1] == 'club/backups/'
    print(json.dumps({'Contents': [{'Key': p.relative_to(root).as_posix()}
                                  for p in root.rglob('*') if p.is_file()]}))
else:
    sys.exit(1)
""")

    def command(self, name, content):
        file = self.root / name
        file.write_text(content)
        file.chmod(0o755)

    def run_backup(self, **overrides):
        env = {**os.environ, 'PATH': f"{self.root}:{os.environ['PATH']}", 'TMPDIR': str(self.work),
               'FIXTURE': str(self.root), 'HIKARI_S3_URI': 's3://example/club', **overrides}
        return subprocess.run(['bash', SCRIPT], env=env, cwd=self.root, capture_output=True, text=True)

    def previous(self, date):
        path = self.backups / f'{date}T050000Z-{UUID}.tar'
        path.write_bytes(b'previous verified backup')
        return path

    def test_retains_three_weeks_and_restores_bundle_files(self):
        obsolete = self.previous("20261030")
        older = self.previous("20261106")
        recent = self.previous("20261113")
        same_week = self.previous("20261118")
        unrelated = self.backups / 'manual-copy.tar'
        unrelated.touch()
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(older.exists() and recent.exists() and unrelated.exists())
        self.assertFalse(obsolete.exists() or same_week.exists())
        archive, = self.backups.glob("20261120*.tar")
        with tarfile.open(archive) as bundle:
            self.assertEqual(set(bundle.getnames()), {'database.dump', 'bot-media.tar', 'admin-media.tar'})
            self.assertEqual(bundle.extractfile('database.dump').read(), b'test-dump')
            with tarfile.open(fileobj=io.BytesIO(bundle.extractfile('bot-media.tar').read())) as media:
                self.assertEqual(media.extractfile('photo.jpg').read(), b'test-image')
            with tarfile.open(fileobj=io.BytesIO(bundle.extractfile('admin-media.tar').read())) as admin:
                self.assertFalse(admin.getmembers())
        self.assertEqual(list(self.work.iterdir()), [])

    def test_corrupt_remote_candidate_does_not_displace_any_backup(self):
        previous = self.previous("20261030")
        result = self.run_backup(CORRUPT='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.backups.iterdir()), [previous])
        self.assertEqual(list((self.root / 'bucket/club/staging').iterdir()), [])
        self.assertEqual(list(self.work.iterdir()), [])

    def test_same_second_winner_is_independent_of_worker(self):
        winner = self.backups / '20261120T120000Z-ffffffff-ffff-ffff-ffff-ffffffffffff.tar'
        winner.write_bytes(b'other successful backup')
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.backups.iterdir()), [winner])

    def test_new_install_with_no_uploads_has_valid_empty_media_archives(self):
        (self.root / "photo.jpg").unlink()
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        archive, = self.backups.glob("*.tar")
        with tarfile.open(archive) as bundle:
            for member in ("bot-media.tar", "admin-media.tar"):
                with tarfile.open(fileobj=io.BytesIO(bundle.extractfile(member).read())) as media:
                    self.assertEqual(media.getmembers(), [])

    def test_refuses_bucket_root_or_parent_path(self):
        for uri in ('s3://example', 's3://example/../club'):
            with self.subTest(uri=uri):
                self.assertNotEqual(self.run_backup(HIKARI_S3_URI=uri).returncode, 0)
                self.assertEqual(list(self.work.iterdir()), [])
