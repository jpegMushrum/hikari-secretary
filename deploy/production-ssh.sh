#!/usr/bin/env bash
set -euo pipefail
: "${DEPLOY_SSH_KEY:?}" "${DEPLOY_KNOWN_HOSTS:?}" "${DEPLOY_HOST:?}" "${DEPLOY_USER:?}"
[[ $DEPLOY_USER =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ && $DEPLOY_HOST != -* ]]
[[ $DEPLOY_PORT =~ ^[0-9]{1,5}$ ]] && (( 10#$DEPLOY_PORT > 0 && 10#$DEPLOY_PORT < 65536 )) || exit 1
remote_command=$(python3 - <<'PY'
import os, re, shlex
path = os.environ["DEPLOY_PATH"]
if not path.startswith("/"):
    raise SystemExit("DEPLOY_PATH must be absolute")
action = os.environ["PRODUCTION_ACTION"]
if action in ("start-santa", "close-santa", "start-mascot", "close-mascot"):
    operation, season = action.split("-")
    command = f"docker compose -f docker-compose.production.yml exec -T backend /app/api {season}-{operation}"
    if operation == "close":
        season_id = os.environ.get("SEASON_ID", "")
        if not re.fullmatch(r"[1-9][0-9]{0,18}", season_id) or int(season_id) > 2**63 - 1:
            raise SystemExit("Enter a positive season ID from the admin panel")
        command += " " + season_id
elif os.environ["PRODUCTION_ACTION"] == "release":
    args = [os.environ[key] for key in ("GITHUB_SHA", "BACKEND_IMAGE", "BOT_IMAGE", "MINIAPP_IMAGE")]
    command = "exec bash -s -- " + shlex.join(args)
else:
    raise SystemExit("Unknown production action")
print("cd " + shlex.quote(path) + " && " + command)
PY
)
umask 077
ssh_dir=$(mktemp -d "$RUNNER_TEMP/deploy-ssh.XXXXXX")
trap 'rm -f "$ssh_dir/key" "$ssh_dir/known_hosts"; rmdir "$ssh_dir"' EXIT
printf '%s\n' "$DEPLOY_SSH_KEY" > "$ssh_dir/key"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$ssh_dir/known_hosts"
input=/dev/null
if [[ $PRODUCTION_ACTION == release ]]; then input=deploy/production-release.sh; fi
ssh -T -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$ssh_dir/known_hosts" -o ConnectTimeout=15 \
  -i "$ssh_dir/key" -p "$DEPLOY_PORT" "$DEPLOY_USER@$DEPLOY_HOST" \
  "$remote_command" < "$input"
