# Insights Inventory

This project is the home of the host-based inventory for the Insights Platform.

## Getting Started

This project uses pip and venv to manage the development and deployment
environments.  To set the project up for development do the following:

```
python -m venv .
. bin/activate
pip install -e .[develop]
```

Also provided are a couple of docker-compose configurations.  The default will
build a container with the Django project and start a database and the wsgi
server.

```
docker-compose up
```

Additionally, the `dev.yml` configuration will simply start a database:

```
docker-compose -f dev.yml up
```

By default the database container will use a bit of local storage so that data
you enter will be persisted across multiple starts of the container.  If you
want to destroy that data do the following:

```
docker-compose down
```

## Running the Tests

Running the tests is quite simple:

```
./manage.py test
```
