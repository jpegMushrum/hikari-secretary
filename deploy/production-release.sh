#!/usr/bin/env bash
# Called from the production checkout with the tested root commit and GHCR digests.
set -euo pipefail
export GIT_TERMINAL_PROMPT=0

fail() { echo "$*" >&2; exit 1; }
[[ $# == 4 ]] || fail "Usage: production-release.sh COMMIT BACKEND_IMAGE BOT_IMAGE MINIAPP_IMAGE"
release=$1
shift
[[ $release =~ ^[0-9a-f]{40}$ ]] || fail "Expected a full Git commit SHA."
components=(backend bot miniapp)
images=("$@")
for i in "${!components[@]}"; do
    pattern="^ghcr\.io/[a-z0-9]+([._-][a-z0-9]+)*/hikari-secretary-${components[i]}@sha256:[0-9a-f]{64}$"
    [[ ${images[i]} =~ $pattern ]] || fail "Expected a GHCR digest for ${components[i]}."
done

[[ -z $(git rev-parse --show-prefix) && $(git branch --show-current) == main ]] ||
    fail "Run from the root of the production main checkout."
[[ -f .env && -w .env ]] || fail "Expected a writable production .env."
exec 9>"$(git rev-parse --git-path hikari-release.lock)"
flock -n 9 || fail "Another production release is in progress."
git diff --quiet --ignore-submodules=all && git diff --cached --quiet ||
    fail "Commit or save tracked checkout changes before deploying."
git submodule foreach --recursive '
    git diff --quiet --ignore-submodules=all && git diff --cached --quiet &&
    { test "$(git rev-parse HEAD)" = "$sha1" || test -n "$(git branch -r --contains HEAD)"; }
'
git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
git merge-base --is-ancestor HEAD "$release" && git merge-base --is-ancestor "$release" origin/main ||
    fail "Release must fast-forward the server and belong to origin/main."
git -c submodule.recurse=false merge --ff-only --no-overwrite-ignore "$release"
git submodule sync --recursive
git submodule update --init --recursive --checkout

export BACKEND_IMAGE=$1 BOT_IMAGE=$2 MINIAPP_IMAGE=$3
compose=(docker compose --env-file .env -f docker-compose.production.yml)
"${compose[@]}" config --quiet
"${compose[@]}" pull backend bot miniapp

# Record the desired state before migrations. A retry or service restart must
# use the same images even when the previous rollout stopped partway through.
python3 deploy/pin_images.py .env "$@"

"${compose[@]}" up -d --no-build --wait --wait-timeout 120 database
# Run the actual one-shot service and propagate its exit status. Waiting for
# it as a long-running service would incorrectly reject a successful exit.
"${compose[@]}" up --no-build --no-deps --force-recreate --exit-code-from backend-migrate backend-migrate
"${compose[@]}" up -d --no-build --no-deps --wait --wait-timeout 120 backend
"${compose[@]}" up -d --no-build --no-deps --wait --wait-timeout 120 bot miniapp
echo "Production release $release is running."
