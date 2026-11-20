"""Exercise the Linux log worker with a journal and S3 transport under test control."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.name == "posix", "The journal worker runs on Linux")
class ArchiveLogsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.work = Path(directory.name)
        self.state = self.work / "state"
        self.state.mkdir()
        self.records = self.work / "records"
        self.records.touch()
        self.objects = self.work / "objects"
        self.objects.mkdir()
        self.write_tool("journalctl", """
import json, pathlib, sys
p = pathlib.Path(".")
args = sys.argv[1:]
tags = {opt.split("=", 1)[1] for opt in args if opt.startswith("CONTAINER_TAG=")}
units = {opt.split("=", 1)[1] for opt in args if opt.startswith("_SYSTEMD_UNIT=")}
seek = next((opt for opt in args if opt.startswith(("--cursor=", "--after-cursor="))), "--cursor=0")
cursor = int(seek.split("=", 1)[1])
skip_first = seek.startswith("--after-cursor=")
for line in (p / "records").read_text().splitlines():
    record = json.loads(line)
    if (record["CONTAINER_TAG"] not in tags or (units and record["_SYSTEMD_UNIT"] not in units)
            or int(record["__CURSOR"]) < cursor):
        continue
    if skip_first:
        skip_first = False
        continue
    print(line)
if (p / "journal-error").exists():
    sys.exit(1)
""")
        self.write_tool("aws", """
import pathlib, shutil, sys
command, operation, source, key, flag = sys.argv[1:]
assert (command, operation, flag) == ("s3", "cp", "--only-show-errors")
assert key.startswith("s3://test-bucket/hikari/logs/")
shutil.copyfile(source, pathlib.Path("objects") / key.split("/")[-1])
if pathlib.Path("delivery-error").exists():
    sys.exit(1)
""")

    def write_tool(self, name, body):
        path = self.work / name
        path.write_text("#!" + sys.executable + "\n" + body)
        path.chmod(0o755)

    def append(self, cursor, tag="hikari-secretary/backend", container="first", unit="docker.service"):
        with self.records.open("a") as stream:
            stream.write(json.dumps({"CONTAINER_TAG": tag, "CONTAINER_ID": container, "_SYSTEMD_UNIT": unit,
                                     "__CURSOR": str(cursor), "__REALTIME_TIMESTAMP": "1704067200000000",
                                     "MESSAGE": "example"}) + "\n")

    def run_worker(self, success=True):
        env = {**os.environ, "PATH": os.pathsep.join((str(self.work), os.environ["PATH"])),
               "HIKARI_S3_URI": "s3://test-bucket/hikari", "STATE_DIRECTORY": str(self.state)}
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("archive_logs.py").resolve())],
                                cwd=self.work, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_resume_after_ambiguous_delivery_and_journal_rotation(self):
        self.append(1)
        self.append(2, tag="another-project/backend")
        self.append(3, container="replacement")
        self.append(4, unit="unrelated.service")
        failure = self.work / "delivery-error"
        failure.touch()
        self.run_worker(success=False)
        self.assertFalse((self.state / "cursor").exists())
        pending = (self.state / "pending.jsonl.gz").read_bytes()
        self.assertEqual([json.loads(line)["__CURSOR"] for line in gzip.decompress(pending).splitlines()],
                         ["1", "3"])
        self.records.write_text("")
        self.append(5, tag="hikari-secretary/bot")
        failure.unlink()
        self.run_worker()
        first_uploads = {p.name: p.read_bytes() for p in self.objects.iterdir()}
        self.assertEqual(len(first_uploads), 2)
        self.assertIn(pending, first_uploads.values())
        self.assertEqual((self.state / "cursor").read_text(), "5")
        self.assertFalse((self.state / "pending.jsonl.gz").exists())
        self.run_worker()
        self.assertEqual({p.name: p.read_bytes() for p in self.objects.iterdir()}, first_uploads)

    def test_empty_or_failed_journal_does_not_advance_checkpoint(self):
        self.run_worker()
        self.append(1)
        (self.work / "journal-error").touch()
        self.run_worker(success=False)
        self.assertFalse((self.state / "cursor").exists())
        self.assertFalse(list(self.objects.iterdir()))

    def test_resume_keeps_all_new_entries_across_vacuum(self):
        for cursor in (1, 2):
            self.append(cursor)
        self.run_worker()
        self.append(3)
        self.run_worker()
        self.records.write_text("")
        for cursor in (4, 5):
            self.append(cursor)
        self.run_worker()
        batches = [[json.loads(line)["__CURSOR"] for line in gzip.decompress(p.read_bytes()).splitlines()]
                   for p in self.objects.iterdir()]
        self.assertCountEqual(batches, [["1", "2"], ["3"], ["4", "5"]])
