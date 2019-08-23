import os

from flask_migrate import Migrate
from flask_migrate import MigrateCommand
from flask_script import Manager  # class for handling a set of commands

from app import create_app
from app import db


app = create_app(config_name=os.getenv("APP_SETTINGS"))
migrate = Migrate(app, db)
manager = Manager(app)

manager.add_command("db", MigrateCommand)


if __name__ == "__main__":
    manager.run()
