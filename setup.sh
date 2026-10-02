#!/usr/bin/env bash
# One command: create the venv, install, and run the tests. No API key needed.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.11+ is required." >&2
  exit 1
fi

"$PYTHON" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e ".[dev]"
.venv/bin/pytest -q

echo
echo "Ready. Try: .venv/bin/draftvoice --help"
