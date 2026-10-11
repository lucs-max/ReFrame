#!/usr/bin/env sh
# Start ReFrame and open it in your browser (Mac/Linux). Keep this window open while you use it.
cd "$(dirname "$0")"
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" -m reframe serve
