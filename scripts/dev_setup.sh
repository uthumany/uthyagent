#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
"$PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("UthyAgent requires Python 3.11 or newer")
PY
if [[ ! -d .venv ]]; then
  "$PYTHON" -m venv --system-site-packages .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
printf '\nSetup complete. Run: %s\n' "$ROOT/scripts/run_dev.sh check"
