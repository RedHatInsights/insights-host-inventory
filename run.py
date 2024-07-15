#!/usr/bin/env python
import os

from app import create_app
from app.environment import RuntimeEnvironment

app = create_app(RuntimeEnvironment.SERVER)


if __name__ == "__main__":
    listen_port = int(os.getenv("LISTEN_PORT", 8080))
    app.run(host="0.0.0.0", port=listen_port)
