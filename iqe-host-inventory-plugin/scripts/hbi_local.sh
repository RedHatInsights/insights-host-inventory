#!/usr/bin/env bash
set -xe


cd ${INSIGHTS_HOST_INVENTORY_CHECKOUT:-~/insights-services/insights-host-inventory}

echo "Running docker-compose to bring up postgres and kafka"
docker-compose -f dev.yml down

# To avoid conflicts when bringing up the services
sudo fuser -k 5432/tcp & # postgres
sudo fuser -k 8080/tcp & # api service
sudo fuser -k 9126/tcp & # mq service
sudo fuser -k 29092/tcp & # kafka
sleep 5

docker-compose -f dev.yml up -d

echo "Setting environment variables"
export INVENTORY_LOG_LEVEL=DEBUG
export KAFKA_BOOTSTRAP_SERVERS="localhost:29092"
export KAFKA_GROUP="inventory"
export KAFKA_HOST_EGRESS_TOPIC="platform.inventory.events"
export REST_POST_ENABLED="false"
export RBAC_ENDPOINT="http://localhost:8000"
export RBAC_ENFORCED="true" # change this value to "true" when running rbac related tests

echo "Creating venv and installing dependencies"
pipenv install
echo venv creation complete

echo "Running DB migrations"
pipenv run python manage.py db upgrade
echo Migration process complete

echo "Running HBI REST API Service"
pipenv run gunicorn -b localhost:8080 run &

echo "Running HBI MQ Service"
pipenv run python inv_mq_service.py &
