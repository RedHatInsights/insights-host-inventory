#!/usr/bin/env bash
set -xe

cd ~/insights-services/insights-rbac

echo "Creating RBAC network"
docker network rm rbac-network || true
docker network create rbac-network || true

echo "Running docker-compose"
docker-compose down

# To avoid conflicts when bringing up the services
sudo fuser -k 6379/tcp & # redis
sudo fuser -k 8000/tcp & # api service
sudo fuser -k 15432/tcp & # postgres
sleep 5

# Create app.log file - otherwise it would be created by containers with 'root' owner
# and the database migration would fail
rm -f rbac/app.log
touch rbac/app.log

docker-compose up -d

echo "Creating RBAC venv"
pipenv --rm || true
pipenv install --dev

echo "Setting environment variables"
cp .env.example .env
#printf "\nDEVELOPMENT=True" >> .env
printf "\nAPI_PATH_PREFIX=/api/rbac" >> .env
printf "\nPRINCIPAL_PROXY_SERVICE_HOST=run.mocky.io" >> .env
printf "\nPRINCIPAL_PROXY_SERVICE_PORT=443" >> .env
printf "\nPRINCIPAL_PROXY_SERVICE_PATH=/v3/e6d47306-a7b7-421d-b0cd-0e2d0e4cf43f" >> .env
printf "\nROLE_CREATE_ALLOW_LIST=inventory" >> .env

echo "Migrating the database"
pipenv run python rbac/manage.py migrate_schemas

echo "Starting the service on port 8000"
pipenv run python rbac/manage.py runserver 0.0.0.0:8000 &
