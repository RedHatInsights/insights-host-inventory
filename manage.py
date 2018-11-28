import os
from flask_script import Manager  # class for handling a set of commands
from flask_migrate import Migrate, MigrateCommand
from app import db, create_app
from app import models

# import models


connexion_app = create_app(config_name=os.getenv('APP_SETTINGS'))
flask_app = connexion_app.app

migrate = Migrate(flask_app.app, db)
manager = Manager(flask_app.app)

manager.add_command('db', MigrateCommand)


if __name__ == '__main__':
    manager.run()
