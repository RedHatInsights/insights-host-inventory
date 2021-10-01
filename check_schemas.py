import json
import sys
from difflib import unified_diff

import yaml

from app.models import SPECIFICATION_DIR
from lib.translating_parser.parser import TranslatingParser

OAPI = SPECIFICATION_DIR + "openapi.json"

with open(OAPI) as fp:
    oapi_data = yaml.dump(json.load(fp))


def make_diff(specfile, output_filename):
    parser = TranslatingParser(SPECIFICATION_DIR + specfile)
    cdiff = unified_diff(
        oapi_data.splitlines(True), parser.yaml().splitlines(True), fromfile="oapi", tofile="output_filename"
    )
    sys.stdout.writelines(cdiff)


if __name__ == "__main__":
    make_diff("openapi.json", "prace_reads_bundle")
    # todo: reenable this once the prance bug about inclusion is resolved
    # make_diff("api.spec.yaml", "prace_reads_spec")
