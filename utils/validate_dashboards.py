#!/usr/bin/env python3
# Originally Authored by Kyle Lape (https://github.com/kylape)
import json
import os
import sys

import yaml


class Error:
    def __init__(self, msg, f):
        self.msg = msg
        self.f = f

    def __repr__(self):
        return f"ERROR {self.f}: {self.msg}"


def validate(f):
    print(f"Validating {f}")
    if not f.endswith(".yaml") and not f.endswith(".yml"):
        yield Error("Bad file name", f)
        return

    try:
        with open(f) as fp:
            y = yaml.safe_load(fp)

        if not y["metadata"].get("name"):
            yield Error("Resource name not found", f)

        d = y["data"]

        if len(d) != 1:
            yield Error("Invalid number of keys in ConfigMap", f)

        key = list(d.keys())[0]

        if not key.endswith(".json"):
            yield Error(f"Key does not end with .json: {key}", f)

        dashboard = json.loads(d[key])
        if "panels" not in dashboard:
            yield Error("Dashboard object is not valid", f)

        print(f"Dashboard {f} successfully validated")
    except Exception as e:
        yield Error(e, f)


seen_error = False

for f in os.listdir("dashboards"):
    for err in validate("dashboards/" + f):
        seen_error = True
        print(err)

if seen_error:
    sys.exit(1)
