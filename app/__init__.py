import os
import connexion

from app.auth import init_app as auth_init_app
from flask_sqlalchemy import SQLAlchemy
from connexion.resolver import RestyResolver


db = SQLAlchemy()


def create_app(config_name):
    connexion_app = connexion.App("inventory", specification_dir='./swagger/',
                                  options={'swagger_ui': False})

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
    user = os.getenv('INVENTORY_DB_USER', 'insights')
    password = os.getenv('INVENTORY_DB_PASS', 'insights')
    host = os.getenv('INVENTORY_DB_HOST', 'localhost')
    db_name = os.getenv('INVENTORY_DB_NAME', 'test_db')
    flask_app.config[
        'SQLALCHEMY_DATABASE_URI'
    ] = f'postgresql://{user}:{password}@{host}/{db_name}'
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    if not flask_app.debug:
        auth_init_app(flask_app)

    db.init_app(flask_app)

    return flask_app
