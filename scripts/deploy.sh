#!/usr/bin/env bash
# Auto-deploys Photoapp when new commits land on main.
#
# Purely pull-based: this script only ever fetches from your own repo and
# compares commit hashes. Nothing listens for anything and nothing reaches
# in from the internet - it's the same trust model as running `git pull`
# yourself, just on a timer.
#
# Usage:
#   ./scripts/deploy.sh
#
# Meant to run on a schedule via cron, e.g. every 5 minutes:
#   */5 * * * * /home/rushi/Photoapp/scripts/deploy.sh >> /var/log/photoapp-deploy.log 2>&1
#
# Override via env vars if your setup differs: REPO_DIR, BRANCH

set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/rushi/Photoapp}"
BRANCH="${BRANCH:-main}"
LOCK_FILE="/tmp/photoapp-deploy.lock"

# Skip this run if a previous one is still building (e.g. a slow first
# Docker build) instead of stacking overlapping deploys.
exec 200>"$LOCK_FILE"
flock -n 200 || exit 0

cd "$REPO_DIR"

git fetch origin "$BRANCH" --quiet

local_commit=$(git rev-parse "$BRANCH")
remote_commit=$(git rev-parse "origin/$BRANCH")

if [ "$local_commit" = "$remote_commit" ]; then
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') New commit on $BRANCH ($remote_commit), deploying..."

git checkout "$BRANCH" --quiet
git reset --hard "origin/$BRANCH"

docker compose up -d --build

echo "$(date '+%Y-%m-%d %H:%M:%S') Deploy complete: now at $(git rev-parse --short HEAD)"
