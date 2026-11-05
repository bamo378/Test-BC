#!/usr/bin/env bash
set -euo pipefail
cd /workspace/Test-BC
python -m pip install --no-cache-dir -r requirements-dev.txt
python -m unittest discover -s tests -v
node tests/frontend.test.js
node tests/pages.test.js
