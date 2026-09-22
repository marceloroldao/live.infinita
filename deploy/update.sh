#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${LIVE_COGNITIVE_BRANCH:-release/server-cognitive-rc1}"

cd "$ROOT"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Tracked local changes detected. Aborting update to avoid overwriting work." >&2
  git status --short >&2
  exit 1
fi

git fetch origin "$BRANCH"
git checkout "$BRANCH"
git merge --ff-only "origin/$BRANCH"

chmod +x deploy/server-cognitive-rc1/*.sh
./deploy/server-cognitive-rc1/bootstrap.sh

if systemctl --user list-unit-files live-infinita-cognitive.service >/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user restart live-infinita-cognitive.service
  systemctl --user --no-pager status live-infinita-cognitive.service || true
else
  echo "Service is not installed yet."
  echo "Run: ./deploy/server-cognitive-rc1/install-service.sh"
fi

echo "Live Infinita Server Cognitive RC1 updated to:"
git rev-parse HEAD
