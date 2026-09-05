#!/usr/bin/env bash
# Auto-deploys Photoapp when new commits land on main, but only once
# GitHub Actions CI has passed for that commit.
#
# Purely pull-based: this script only ever fetches from your own repo and
# GitHub's API, and compares commit hashes / CI status. Nothing listens for
# anything and nothing reaches in from the internet - it's the same trust
# model as running `git pull` yourself, just on a timer with a CI check
# gating it first.
#
# Usage:
#   ./scripts/deploy.sh
#
# Meant to run on a schedule via cron, e.g. every 5 minutes:
#   */5 * * * * /home/rushi/Photoapp/scripts/deploy.sh >> /home/rushi/photoapp-logs/deploy.log 2>&1
#
# Override via env vars if your setup differs: REPO_DIR, REPO, BRANCH
# Requires: git, curl, jq, docker (with the compose plugin).

set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/rushi/Photoapp}"
REPO="${REPO:-ruship527/self-hosted-photo-manager}"
BRANCH="${BRANCH:-main}"
LOCK_FILE="/tmp/photoapp-deploy.lock"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*"
}

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

log "New commit on $BRANCH ($remote_commit), checking CI before deploying..."

# Only deploy once GitHub Actions CI has finished and passed for the new
# commit - this is what actually makes it safe to auto-deploy unattended.
check_runs=$(curl -sf "https://api.github.com/repos/$REPO/commits/$remote_commit/check-runs") || {
    log "Failed to query CI status from GitHub, will retry next run"
    exit 0
}

total=$(echo "$check_runs" | jq '.total_count')
incomplete=$(echo "$check_runs" | jq '[.check_runs[] | select(.status != "completed")] | length')
failed=$(echo "$check_runs" | jq '[.check_runs[] | select(.conclusion != "success" and .conclusion != null)] | length')

if [ "$total" -eq 0 ]; then
    log "No CI checks reported yet for $remote_commit, will retry next run"
    exit 0
fi

if [ "$incomplete" -gt 0 ]; then
    log "CI still running for $remote_commit, will retry next run"
    exit 0
fi

if [ "$failed" -gt 0 ]; then
    log "CI failed for $remote_commit - NOT deploying"
    exit 1
fi

log "CI passed, deploying..."

git checkout "$BRANCH" --quiet
git reset --hard "origin/$BRANCH"

docker compose up -d --build

log "Deploy complete: now at $(git rev-parse --short HEAD)"
