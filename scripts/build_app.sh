#!/usr/bin/env bash
# Build LinkBridge.app with py2app.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    if [[ -f venv/bin/activate ]]; then
        # shellcheck disable=SC1091
        source venv/bin/activate
    else
        echo "Error: no venv/ found and VIRTUAL_ENV is not set" >&2
        exit 1
    fi
fi

echo "Cleaning previous build artifacts..."
rm -rf build dist

echo "Running py2app..."
python setup.py py2app

echo
echo "Built: dist/LinkBridge.app"
