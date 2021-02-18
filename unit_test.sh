#!/bin/bash

APP_NAME="host-inventory"  # name of app-sre "application" folder this component lives in
IMAGE="quay.io/cloudservices/insights-inventory"
BG_PID=1010101
RANDOM_PORT=62212
export LC_ALL=en_US.utf-8
export LANG=en_US.utf-8

python3.6 -m venv venv
source venv/bin/activate
pip install pipenv
pipenv install --dev

if ! (pre-commit run --all-files); then
  echo "pre-commit ecountered an issue"
  exit 1
fi

# --------------------------------------------
# Unit testing Django
# --------------------------------------------

function killbg {
  echo "Caught signal, kill port forward"
  kill $BG_PID
}

function nsrelease {
  echo "Release bonfire namespace"
  bonfire namespace release $NAMESPACE
}

function random_unused_port { local port=$(shuf -i 2000-65000 -n 1)
    netstat -lat | grep $port > /dev/null
    if [[ $? == 1 ]] ; then
        RANDOM_PORT=$port
    else
        random_unused_port
    fi
}

#
# Install Bonfire
#
if ! (which bonfire >/dev/null); then
  # Pin to local config change commit to avoid other breaking changes until
  # Bonfire has new refactor settled
  pip install "git+https://github.com/RedHatInsights/bonfire.git@e5321c3dab481f7d607f0609d8d2ec0a83f3bead#egg=crc_bonfire"
fi

#
# Deploy ClowdApp to get DB instance
#

NAMESPACE=$(bonfire namespace reserve)
oc project $NAMESPACE

cat << EOF > config.yaml
envName: env-$NAMESPACE
apps:
- name: host-inventory
  host: local
  repo: $PWD
  path: deployment.yaml
  parameters:
    IMAGE: $IMAGE
EOF

bonfire local get --set-image-tag ${APP_NAME}=${IMAGE_TAG} -a ${APP_NAME} | oc apply -f -

# Wait on the App to be Ready. Do not run unit tests if you do not become Ready.
bonfire namespace wait-on-resources $NAMESPACE || { echo 'App did not deploy properly' ; exit 1; }

#
# Grab DB creds
#

# Get a random port on the jenkins agent to forward
echo "Getting a port to forward"
# random_unused_port

echo "Parsing secret details"
oc get secret ${APP_NAME} -o json | jq -r '.data["cdappconfig.json"]' | base64 -d | jq .database > db-creds.json

export INVENTORY_DB_NAME=$(jq -r .name < db-creds.json)
export INVENTORY_DB_HOST=localhost
export INVENTORY_DB_PORT=$RANDOM_PORT
export INVENTORY_DB_USER=$(jq -r .adminUsername < db-creds.json)
export INVENTORY_DB_PASS=$(jq -r .adminPassword < db-creds.json)
export PGPASSWORD=$(jq -r .adminPassword < db-creds.json)

oc port-forward svc/${APP_NAME}-db $RANDOM_PORT:5432 &
BG_PID=$!
trap "killbg" EXIT ERR SIGINT SIGKILL TERM
trap "nsrelease" EXIT ERR SIGINT SIGKILL TERM

echo "DB migration"
python manage.py db upgrade
echo "Running pytest"
pytest --cov=. --junitxml=junit.xml --cov-report html -sv

mkdir -p $WORKSPACE/artifacts
cp junit.xml ${WORKSPACE}/artifacts/junit.xml
nsrelease
