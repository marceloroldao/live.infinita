#!/usr/bin/env bash
# Compatibility: the original 008DS rollout required real resident floor colliders.
set -Eeuo pipefail
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/apply-physical-wildlife-008ds1-root.sh" "$@"
