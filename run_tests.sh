#!/usr/bin/env bash
# Runs every check: build freshness, local connector, Worker connector, share page, radio.
set -euo pipefail
cd "$(dirname "$0")"
python3 build.py --check
python3 -m unittest discover tests
node --test tests/test_worker.mjs
python3 tests/page_check.py
python3 tests/radio_check.py
# The one-page v2 preview (docs/v2/), same page and radio checks
if [ -f docs/v2/index.html ]; then
  PAGE=v2/ python3 tests/page_check.py
  PAGE=v2/ python3 tests/radio_check.py
fi
