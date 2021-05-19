import json
import sys
from difflib import unified_diff

import yaml

from app.models import SPECIFICATION_DIR
from lib.translating_parser.parser import TranslatingParser

OAPI = SPECIFICATION_DIR + "openapi.json"

with open(OAPI) as fp:
    oapi_data = yaml.dump(json.load(fp))

openapi = TranslatingParser(OAPI)
openapi.parse()

# spec = TranslatingParser(SPECIFICATION_DIR + "api.spec.yaml")
# spec.parse()


cdiff = unified_diff(oapi_data.splitlines(True), openapi.yaml().splitlines(True), fromfile="oapi", tofile="prance")
sys.stdout.writelines(cdiff)
