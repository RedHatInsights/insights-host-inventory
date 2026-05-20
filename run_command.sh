#!/bin/bash

if [ "$#" -eq 0 ]; then
    echo "ERROR: No command provided to run."
    exit 1
fi

APP_ROOT="${APP_ROOT:-/opt/app-root/src}"
VENV_PYTHON="${APP_ROOT}/.venv/bin/python"

# Export leading VAR=value arguments (e.g. FLASK_APP=./manage.py flask db upgrade)
while [[ $# -gt 0 && "$1" == *'='* ]]; do
    export "$1"
    shift
done

if [ "$#" -eq 0 ]; then
    echo "ERROR: Only environment assignments provided, no command to run."
    exit 1
fi

# If args contain shell operators (&&, ||, ;), delegate to sh -c for interpretation.
# This handles ClowdApp args like ["./script_a.py", "&&", "./script_b.py"].
for arg in "$@"; do
    if [[ "$arg" == "&&" || "$arg" == "||" || "$arg" == ";" || "$arg" == "|" ]]; then
        exec /bin/sh -c "$*"
    fi
done

# ClowdApp runs scripts as ./foo.py; the shebang must not use /usr/bin/python because
# that is the RPM interpreter without project deps. Run .py entrypoints with the venv.
if [ -x "$VENV_PYTHON" ] && [[ "$1" == *'.py' ]]; then
    exec "$VENV_PYTHON" "$@"
fi

exec "$@"
