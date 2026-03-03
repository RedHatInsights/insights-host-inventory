#!/bin/bash
set -e

cd ./tools/simple-test/
source venv/bin/activate
python tester.py ../../swagger/system_profile.spec.yaml ./output.json
