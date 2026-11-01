#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$ROOT/.venv/bin/uthyagent" ]]; then
  echo "Development environment not found. Run scripts/dev_setup.sh first." >&2
  exit 2
fi
exec "$ROOT/.venv/bin/uthyagent" "$@"
