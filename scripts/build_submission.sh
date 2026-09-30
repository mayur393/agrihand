#!/usr/bin/env bash
# Build submission.tar.gz (main.py + config.py at the archive root) after the
# compliance precheck passes. Upload the result with:
#   kaggle competitions submit kaggriculture -f submission.tar.gz -m "<message>"
# or via the "Submit Agent" button on the competition page.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-.venv/bin/python}
[ -x "$PY" ] || PY=python3

"$PY" scripts/precheck_submission.py
rm -f submission.tar.gz
tar -czf submission.tar.gz main.py config.py

echo "--- submission.tar.gz"
tar -tzf submission.tar.gz
sha256sum submission.tar.gz main.py config.py
