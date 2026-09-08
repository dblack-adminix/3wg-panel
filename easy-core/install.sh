#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PANEL_EDITION=easy
exec bash "$ROOT/scripts/install.sh" "$@"
