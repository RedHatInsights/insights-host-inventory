#!/bin/bash
set -e

function is_gunicorn_installed() {
  hash gunicorn &>/dev/null
}

function is_django_installed() {
  python -c "import django" &>/dev/null
}

# Guess the number of workers according to the number of cores
function get_default_web_concurrency() {
  limit_vars=$(cgroup-limits)
  local $limit_vars
  if [ -z "${NUMBER_OF_CORES:-}" ]; then
    echo 1
    return
  fi

  local max=$((NUMBER_OF_CORES*2))
  # Require at least 43 MiB and additional 40 MiB for every worker
  local default=$(((${MEMORY_LIMIT_IN_BYTES:-MAX_MEMORY_LIMIT_IN_BYTES}/1024/1024 - 43) / 40))
  default=$((default > max ? max : default))
  default=$((default < 1 ? 1 : default))
  # According to http://docs.gunicorn.org/en/stable/design.html#how-many-workers,
  # 12 workers should be enough to handle hundreds or thousands requests per second
  default=$((default > 12 ? 12 : default))
  echo $default
}

APP_HOME=${APP_HOME:-.}
# Look for 'manage.py' in the directory specified by APP_HOME, or the current direcotry
manage_file=$APP_HOME/manage.py

echo "---> Collecting static files ..."
python "$manage_file" collectstatic --noinput

export WEB_CONCURRENCY=${WEB_CONCURRENCY:-$(get_default_web_concurrency)}
echo "Web concurrency is $WEB_CONCURRENCY"

echo "---> Serving application with gunicorn ($APP_MODULE) ..."
exec gunicorn "insights.wsgi" --bind=0.0.0.0:${GUNICORN_PORT:-8080} --access-logfile=- --config "$APP_CONFIG"
