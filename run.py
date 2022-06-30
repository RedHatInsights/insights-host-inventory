#!/usr/bin/env python
import os

from waitress import serve

from app import create_app
from app.environment import RuntimeEnvironment

application = create_app(RuntimeEnvironment.SERVER)

if __name__ == "__main__":
    listen_port = int(os.getenv("LISTEN_PORT", 8080))

    if os.environ.get("FLASK_ENV") == "production":
        serve(application, host="0.0.0.0", port=listen_port)
    else:
        application.run(host="0.0.0.0", port=listen_port)
