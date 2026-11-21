#!/usr/bin/env bash
# Run from the production checkout via hikari-backup@.service.
set -euo pipefail
umask 077
export AWS_PAGER="" LC_ALL=C

uri=${HIKARI_S3_URI:?Set HIKARI_S3_URI to s3://bucket/project}
if [[ ! $uri =~ ^s3://([a-z0-9][a-z0-9.-]*)/([a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*)$ ]]; then
    echo "Expected HIKARI_S3_URI=s3://bucket/project with a dedicated prefix" >&2
    exit 1
fi
bucket=${BASH_REMATCH[1]}
prefix=${BASH_REMATCH[2]}/backups/
id="$(date -u +%Y%m%dT%H%M%SZ)-$(cat /proc/sys/kernel/random/uuid)"
work=$(mktemp -d "${TMPDIR:-/var/tmp}/hikari-backup.XXXXXXXX")
candidate="$uri/staging/$id.tar"
uploaded=false
cleanup() {
    rm -rf -- "$work"
    if [[ $uploaded == true ]]; then
        aws s3 rm "$candidate" --only-show-errors || echo "Could not clean up the staging object" >&2
    fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

compose=(docker compose --env-file .env -f docker-compose.production.yml exec -T)
"${compose[@]}" database sh -ec 'exec pg_dump --format=custom -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$work/database.dump"
"${compose[@]}" database pg_restore --list < "$work/database.dump" > /dev/null

# Media directories may not exist until the first upload or bot startup.
archive_media() {
    local service=$1
    "${compose[@]}" "$service" sh -ec '
        if [ "$1" = bot ]; then
            dir=${MEDIA_DIR:-/app/data/media}
        else
            dir=${ADMIN_MEDIA_DIR:-data/admin-media}
        fi
        resolved=$(readlink -f "$dir")
        case "$resolved" in /app/data/?*) ;; *) echo "Expected a media directory inside /app/data" >&2; exit 1;; esac
        if [ ! -e "$dir" ] && [ ! -L "$dir" ] && [ -x "$(dirname "$resolved")" ]; then exit 42; fi
        exec tar -C "$resolved" -cf - .
    ' sh "$service" > "$work/$2" || {
        local status=$?
        if [[ $status == 42 ]]; then
            tar -cf "$work/$2" --files-from /dev/null
        else
            return "$status"
        fi
    }
}
archive_media bot bot-media.tar
archive_media backend admin-media.tar
tar -C "$work" -cf "$work/bundle.tar" database.dump bot-media.tar admin-media.tar
checksum=$(sha256sum < "$work/bundle.tar")

uploaded=true
aws s3 cp "$work/bundle.tar" "$candidate" --only-show-errors
remote_checksum=$(aws s3 cp "$candidate" - --only-show-errors | sha256sum)
[[ $checksum == "$remote_checksum" ]] || { echo "Backup checksum mismatch" >&2; exit 1; }
# Only verified bundles are promoted into the collection used for rotation.
aws s3 cp "$candidate" "$uri/backups/$id.tar" --copy-props none --only-show-errors
aws s3api list-objects-v2 --bucket "$bucket" --prefix "$prefix" --output json > "$work/keys.json"
python3 - "$work/keys.json" "$prefix" "${id%%-*}" > "$work/expired" <<'PY'
import json
import re
import sys
from datetime import datetime, timedelta

with open(sys.argv[1]) as listing:
    objects = json.load(listing).get("Contents", [])
name = re.compile(re.escape(sys.argv[2]) + r"([0-9]{8}T[0-9]{6}Z)-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\.tar")
timestamp_format = "%Y%m%dT%H%M%SZ"
cutoff = datetime.strptime(sys.argv[3], timestamp_format) - timedelta(days=365)
weeks = set()
keys = (obj["Key"] for obj in objects)
# Managed keys sort by UTC timestamp then UUID, consistently across workers.
for key in sorted(keys, reverse=True):
    match = name.fullmatch(key)
    if not match:
        continue
    try:
        timestamp = datetime.strptime(match[1], timestamp_format)
    except ValueError:
        continue
    week = timestamp.isocalendar()[:2]
    if timestamp < cutoff or week in weeks:
        print(key)
    else:
        weeks.add(week)
PY
while IFS= read -r key; do
    aws s3 rm "s3://$bucket/$key" --only-show-errors
done < "$work/expired"
printf 'Backup verified: %s. Weekly retention applied.\n' "$id.tar"
