from flask_api import FlaskAPI
from flask_sqlalchemy import SQLAlchemy

from connexion.resolver import RestyResolver
import connexion

# local import
#from instance.config import app_config

# initialize sql-alchemy
db = SQLAlchemy()


def create_app(config_name):
    #app = FlaskAPI(__name__, instance_relative_config=True)
    #app.config.from_object(app_config[config_name])
    #app.config.from_pyfile('config.py')
    #app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    connexion_app = connexion.App("inventory", specification_dir='./swagger/')


    # Read the swagger.yml file to configure the endpoints
    connexion_app.add_api('api.spec.yaml',
            arguments={'title':'RestyResolver Example'},
            resolver=RestyResolver("api"),
            validate_response=True,
            strict_validation=True)

    flask_app = connexion_app.app

    flask_app.config['SQLALCHEMY_ECHO'] = True 
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://insights:insights@localhost/test_db'
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    print("Calling db.init_app()")
    db.init_app(flask_app)

    return flask_app
