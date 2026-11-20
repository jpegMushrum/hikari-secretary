"""Upload production container journal entries in resumable gzip batches."""
import fcntl
import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess


SERVICES = ("database", "backend-migrate", "backend", "bot", "miniapp", "backend-import", "legacy-snapshot")
BATCH_BYTES = 4 * 1024 * 1024


def save(path, data):
    """Keep either the old or the new complete file across a crash."""
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    sync_directory(path.parent)


def sync_directory(path):
    descriptor = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def upload_pending(state, destination):
    pending = state / "pending.jsonl.gz"
    # The last entry in the durable batch contains its checkpoint. Keeping the
    # two together allows a retry even if journald has already rotated them.
    with gzip.open(pending, "rb") as stream:
        for line in stream:
            last = line
    record = json.loads(last)
    cursor = record["__CURSOR"].encode("utf-8")
    timestamp = datetime.fromtimestamp(int(record["__REALTIME_TIMESTAMP"]) // 1_000_000, timezone.utc)
    digest = hashlib.sha256(cursor).hexdigest()
    key = f"{destination}/logs/{timestamp:%Y/%m/%d/%H%M%S}-{digest}.jsonl.gz"
    subprocess.run(["aws", "s3", "cp", str(pending), key, "--only-show-errors"], check=True)
    save(state / "cursor", cursor)
    pending.unlink()
    sync_directory(state)


def archive(state, destination):
    if not re.fullmatch(r"s3://[a-z0-9][a-z0-9.-]*(?:/[A-Za-z0-9_-]+)+", destination):
        raise ValueError("HIKARI_S3_URI must name an S3 bucket and a nonempty project prefix")
    pending = state / "pending.jsonl.gz"
    if pending.exists():
        upload_pending(state, destination)

    args = ["journalctl", "--quiet", "--no-pager", "--all", "--output=json",
            "--output-fields=MESSAGE,CONTAINER_TAG,CONTAINER_ID,PRIORITY"]
    checkpoint = state / "cursor"
    previous = checkpoint.read_text(encoding="utf-8") if checkpoint.exists() else None
    if previous is not None:
        args.append("--cursor=" + previous)
    # Require the trusted source unit as well as a matching container tag.
    args.append("_SYSTEMD_UNIT=docker.service")
    # journalctl treats alternatives for the same field as OR.
    args.extend("CONTAINER_TAG=hikari-secretary/" + service for service in SERVICES)

    with subprocess.Popen(args, stdout=subprocess.PIPE) as reader:
        batch = bytearray()
        for line in reader.stdout:
            if previous is not None:
                # Vacuuming can move the seek position to the oldest surviving
                # entry. Skip only the exact record we have already delivered.
                already_delivered = json.loads(line)["__CURSOR"] == previous
                previous = None
                if already_delivered:
                    continue
            batch.extend(line)
            if len(batch) >= BATCH_BYTES:
                save(pending, gzip.compress(batch, compresslevel=3, mtime=0))
                upload_pending(state, destination)
                batch.clear()
        if reader.wait() != 0:
            raise RuntimeError("journalctl could not read the production container logs")
        if batch:
            save(pending, gzip.compress(batch, compresslevel=3, mtime=0))
            upload_pending(state, destination)


if __name__ == "__main__":
    os.umask(0o077)
    state = Path(os.environ["STATE_DIRECTORY"])
    with (state / "logs.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        archive(state, os.environ["HIKARI_S3_URI"])
