#!/usr/bin/env python
import json
import os

from app import create_app
from app.environment import RuntimeEnvironment

application = create_app(RuntimeEnvironment.SERVER)
app = application.app
scrubbed_apis = ["assignment-rules"]


@app.after_request
def after_request(response):
    if response.status_code != 200:
        return
    response_text = response.get_data(as_text=True)
    if "openapi" not in response_text:
        return

    try:
        response_json = json.loads(response_text)
    except ValueError:
        return response

    paths_to_delete = []
    for path in response_json.get("paths", {}).keys():
        for api in scrubbed_apis:
            if api in path:
                paths_to_delete.append(path)
    for path in paths_to_delete:
        del response_json["paths"][path]
    try:
        response_text = json.dumps(response_json)
    except ValueError:
        return response

    response.set_data(response_text)
    return response


if __name__ == "__main__":
    listen_port = int(os.getenv("LISTEN_PORT", 8080))
    application.run(host="0.0.0.0", port=listen_port)
