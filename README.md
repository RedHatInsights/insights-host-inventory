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

## Basic testing

To test creating a sample host, you may simply send a simple JSON request like
this:

```
curl -H 'X_RH_IDENTITY: foobar' -H 'Content-Type: application/json' -X POST localhost:8000/api/hosts/ -d '{ "display_name": "foo", "account": "bar" }'
```

After that, you can run the following command to ensure the test host 'foo' was
registered and appears in the list of hosts.


```
curl -H 'X_RH_IDENTITY: foobar' -v http://localhost:8000/api/hosts/?format=json
```

All requests are authenticated by the user in the header 'X_RH_IDENTITY'


## Running the Tests

Running the tests is quite simple:

```
./manage.py test
```
