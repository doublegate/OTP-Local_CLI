#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONPATH="$PWD/src:$PWD/tests"
.venv/bin/python scripts/bundle_guides.py --check
# Installer contracts need a wheel built from the current source tree.
.venv/bin/python -m build --no-isolation
# Stage dependency wheels into wheelhouse for isolated offline smoke tests.
.venv/bin/pip wheel --wheel-dir dist/wheels --quiet "textual>=0.80.0"
.venv/bin/python -m coverage run -m pytest tests -v
.venv/bin/python -m coverage report
.venv/bin/python -m coverage report --include='*/models.py,*/backends/onepassword.py' --fail-under=100
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
shellcheck scripts/check.sh
node_modules/.bin/markdownlint-cli2 --config .markdownlint-cli2.jsonc
.venv/bin/python scripts/check_docs.py
.venv/bin/python scripts/smoke_package.py
