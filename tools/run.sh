#!/bin/bash
# Runs one of the Python tools from the project root, with tools/ on PYTHONPATH.
# Needs Python 3 with numpy and Pillow (pip install numpy pillow).
# If they are not installed but cached wheels exist (Kiro sandbox, read-only home),
# the wheels are unpacked into /dev/shm and used instead.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTRA=""
if ! python3 -c "import numpy, PIL" 2>/dev/null; then
  LIB=/dev/shm/pylibs
  WHEELS=/projects/sandbox/.cache/wheels
  if ! ls "$WHEELS"/*.whl >/dev/null 2>&1; then
    echo "numpy and Pillow are required: pip install numpy pillow" >&2
    exit 1
  fi
  if [ ! -d "$LIB/numpy" ] || [ ! -d "$LIB/PIL" ]; then
    mkdir -p "$LIB"
    for w in "$WHEELS"/*.whl; do unzip -q -o "$w" -d "$LIB"; done
  fi
  EXTRA="$LIB:"
fi
cd "$ROOT"
PYTHONPATH="${EXTRA}$ROOT/tools" exec python3 "$@"
