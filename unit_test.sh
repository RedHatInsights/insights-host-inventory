#!/bin/bash

cd $APP_ROOT

# Deploy ephemeral db
source $CICD_ROOT/deploy_ephemeral_db.sh

# Map env vars set by `deploy_ephemeral_db.sh` if vars the app uses are different
export INVENTORY_DB_NAME=$DATABASE_NAME
export INVENTORY_DB_HOST=$DATABASE_HOST
export INVENTORY_DB_PORT=$DATABASE_PORT
export INVENTORY_DB_USER=$DATABASE_USER
export INVENTORY_DB_PASS=$DATABASE_PASSWORD
export PGPASSWORD=$DATABASE_ADMIN_PASSWORD


# check python version before
python --version

# Setup venv for unit tests
python3.8 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel pipenv
pipenv install --dev

# Run pre-commit
if ! (pre-commit run --all-files); then
  echo "pre-commit ecountered an issue"
  exit 1
fi

# Run unit tests
python manage.py db upgrade
echo "Running pytest"
pytest --cov=. --junitxml=junit-unittest.xml --cov-report html -sv

result=$?

# Move back out of app virtual env
deactivate

mkdir -p $WORKSPACE/artifacts
cp junit-unittest.xml ${WORKSPACE}/artifacts/junit-unittest.xml

cd -

exit $result
