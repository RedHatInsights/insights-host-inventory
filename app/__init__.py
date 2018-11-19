import os
import connexion

from app.auth import init_app as auth_init_app
from flask_sqlalchemy import SQLAlchemy
from connexion.resolver import RestyResolver


db = SQLAlchemy()


def _build_database_uri():
    user = os.getenv('INVENTORY_DB_USER', 'insights')
    password = os.getenv('INVENTORY_DB_PASS', 'insights')
    host = os.getenv('INVENTORY_DB_HOST', 'localhost')
    db_name = os.getenv('INVENTORY_DB_NAME', 'test_db')

    return f'postgresql://{user}:{password}@{host}/{db_name}'


def _get_db_pool_timeout():
    return int(os.getenv('INVENTORY_DB_POOL_TIMEOUT', '5'))


def _get_db_pool_size():
    return int(os.getenv('INVENTORY_DB_POOL_SIZE', '5'))


def create_app(config_name):
    connexion_options = {'swagger_ui': False}

    if config_name == "development":
        connexion_options['swagger_ui'] = True

    connexion_app = connexion.App("inventory",
                                  specification_dir='./swagger/',
                                  options=connexion_options)

    # Read the swagger.yml file to configure the endpoints
    connexion_app.add_api(
        'api.spec.yaml',
        arguments={'title': 'RestyResolver Example'},
        resolver=RestyResolver("api"),
        validate_responses=True,
        strict_validation=True,
    )

    flask_app = connexion_app.app

    flask_app.config['SQLALCHEMY_ECHO'] = False
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = _build_database_uri()
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    flask_app.config['SQLALCHEMY_POOL_SIZE'] = _get_db_pool_size()
    flask_app.config['SQLALCHEMY_POOL_TIMEOUT'] = _get_db_pool_timeout()

    if not flask_app.debug:
        auth_init_app(flask_app)

    db.init_app(flask_app)

    return flask_app
