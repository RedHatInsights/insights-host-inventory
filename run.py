#!/usr/bin/env python
import os

from app import create_app
from app.environment import RuntimeEnvironment

application = create_app(RuntimeEnvironment.SERVER)
app = application.app


if __name__ == "__main__":
    listen_port = int(os.getenv("LISTEN_PORT", 8080))
    application.run(host="0.0.0.0", port=listen_port)
