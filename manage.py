from flask_migrate import Migrate
from flask_migrate import MigrateCommand
from flask_script import Manager  # class for handling a set of commands

from app import create_app
from app import db
from app.environment import RuntimeEnvironment


app = create_app(RuntimeEnvironment.COMMAND)
migrate = Migrate(app, db)
manager = Manager(app)

manager.add_command("db", MigrateCommand)


if __name__ == "__main__":
    manager.run()
