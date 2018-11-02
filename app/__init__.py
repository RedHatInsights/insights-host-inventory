import os
import logging
import connexion
from flask_api import FlaskAPI
from flask_sqlalchemy import SQLAlchemy
from connexion.resolver import RestyResolver


LOGLEVEL = os.environ.get('INVENTORY_LOGLEVEL', 'WARNING')
logging.basicConfig(level=LOGLEVEL.upper())

db = SQLAlchemy()


def create_app(config_name):
    # app = FlaskAPI(__name__, instance_relative_config=True)
    # app.config.from_object(app_config[config_name])
    # app.config.from_pyfile('config.py')
    # app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    connexion_app = connexion.App("inventory", specification_dir='./swagger/')

    # Read the swagger.yml file to configure the endpoints
    connexion_app.add_api(
        'api.spec.yaml',
        arguments={'title': 'RestyResolver Example'},
        resolver=RestyResolver("api"),
        validate_response=True,
        strict_validation=True,
    )

    flask_app = connexion_app.app

    flask_app.config['SQLALCHEMY_ECHO'] = False
    user = os.getenv('INVENTORY_DB_USER', 'insights')
    password = os.getenv('INVENTORY_DB_PASS', 'insights')
    host = os.getenv('INVENTORY_DB_HOST', 'localhost')
    db_name = os.getenv('INVENTORY_DB_NAME', 'test_db')
    flask_app.config[
        'SQLALCHEMY_DATABASE_URI'
    ] = f'postgresql://{user}:{password}@{host}/{db_name}'
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(flask_app)

    return flask_app
