import json
import sys
from difflib import unified_diff

import yaml
from prance import _TranslatingParser as TranslatingParser

from app.models import SPECIFICATION_DIR

OAPI = SPECIFICATION_DIR + "openapi.json"

with open(OAPI) as fp:
    oapi_data = yaml.dump(json.load(fp))


def make_diff(specfile, output_filename):
    parser = TranslatingParser(SPECIFICATION_DIR + specfile)
    cdiff = unified_diff(
        oapi_data.splitlines(True), parser.yaml().splitlines(True), fromfile="oapi", tofile=output_filename
    )
    sys.stdout.writelines(cdiff)


if __name__ == "__main__":
    make_diff("openapi.json", "prance_reads_bundle")
    # TODO: reenable this once the prance bug about inclusion is resolved
    # make_diff("api.spec.yaml", "prace_reads_spec")
