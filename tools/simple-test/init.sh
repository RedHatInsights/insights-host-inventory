#!/bin/bash
set -e

cd tools/simple-test/
uv venv venv
source venv/bin/activate
uv pip install -r requirements.txt
