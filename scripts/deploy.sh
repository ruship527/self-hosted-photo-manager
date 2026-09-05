#!/usr/bin/env bash
# Polls GitHub for new commits on `main` and, only once GitHub Actions CI
# has passed for that commit, pulls it and redeploys via Docker Compose.
#
# Meant to run on a short interval via cron - it's a safe no-op unless
# origin/main has actually moved past the local HEAD:
#   */5 * * * * /home/rushi/Photoapp/scripts/deploy.sh >> /home/rushi/photoapp-logs/deploy.log 2>&1
#
# Requires: git, curl, jq, docker (with the compose plugin).

set -euo pipefail

REPO_DIR="/home/rushi/Photoapp"
REPO="ruship527/self-hosted-photo-manager"
BRANCH="main"

log() {
    echo "$(date -Iseconds) $*"
}

# Prevent overlapping runs in case a previous deploy is still building
# when the next cron tick fires.
LOCK_FILE="/tmp/photoapp-deploy.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    log "a deploy is already in progress, skipping this run"
    exit 0
fi

cd "$REPO_DIR"

git fetch origin "$BRANCH" --quiet

local_sha=$(git rev-parse HEAD)
remote_sha=$(git rev-parse "origin/$BRANCH")

if [ "$local_sha" = "$remote_sha" ]; then
    exit 0
fi

log "new commit on $BRANCH: $remote_sha (currently running $local_sha)"

if [ -n "$(git status --porcelain)" ]; then
    log "local working tree has uncommitted changes, refusing to deploy"
    exit 1
fi

# Only deploy once GitHub Actions CI has finished and passed for the new
# commit. This is what actually makes it safe to auto-deploy unattended.
check_runs=$(curl -sf "https://api.github.com/repos/$REPO/commits/$remote_sha/check-runs") || {
    log "failed to query CI status from GitHub, will retry next run"
    exit 0
}

total=$(echo "$check_runs" | jq '.total_count')
incomplete=$(echo "$check_runs" | jq '[.check_runs[] | select(.status != "completed")] | length')
failed=$(echo "$check_runs" | jq '[.check_runs[] | select(.conclusion != "success" and .conclusion != null)] | length')

if [ "$total" -eq 0 ]; then
    log "no CI checks reported yet for $remote_sha, will retry next run"
    exit 0
fi

if [ "$incomplete" -gt 0 ]; then
    log "CI still running for $remote_sha, will retry next run"
    exit 0
fi

if [ "$failed" -gt 0 ]; then
    log "CI failed for $remote_sha - NOT deploying"
    exit 1
fi

log "CI passed for $remote_sha, deploying..."
git pull origin "$BRANCH" --quiet
docker compose up -d --build
log "deploy complete, now running $(git rev-parse HEAD)"
