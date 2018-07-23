# Insights Inventory

This project is the home of the host-based inventory for the Insights Platform.

## Getting Started

This project uses pipenv to manage the development and deployment environments.
To set the project up for development do the following:

```
pipenv install --dev
```

Afterwards you can activate the virtual environment by running:

```
pipenv shell
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

### (optional) Static files

For development environment run collectstatic to get static files as described
at `insights/settings.py`.

```
python manage.py collectstatic
```

### (optional) Populate DB

From pipenv shell run script below to add initial data into DB table:

```
python -m inventory.populate
```

## Running the Tests

Running the tests is quite simple:

```
./manage.py test
```

