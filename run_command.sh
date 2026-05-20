#!/bin/bash

if [ "$#" -eq 0 ]; then
    echo "ERROR: No command provided to run."
    exit 1
fi

APP_ROOT="${APP_ROOT:-/opt/app-root/src}"
VENV_PYTHON="${APP_ROOT}/.venv/bin/python"

# ClowdApp runs scripts as ./foo.py; the shebang must not use /usr/bin/python because
# that is the RPM interpreter without project deps. Run .py entrypoints with the venv.
# Skip env assignments (e.g. FLASK_APP=./manage.py flask db upgrade).
if [ -x "$VENV_PYTHON" ] && [[ "$1" == *'.py' ]] && [[ "$1" != *'='* ]]; then
    exec "$VENV_PYTHON" "$@"
fi

exec "$@"
