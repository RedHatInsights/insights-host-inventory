#!/bin/bash

pip3 install pip-tools pybuild-deps
pip3 install "pip<25"
# cd /tmp
# wget -c https://raw.githubusercontent.com/containerbuildsystem/cachito/master/bin/pip_find_builddeps.py
# chmod a+x pip_find_builddeps.py
cd /var/tmp
# /tmp/pip_find_builddeps.py requirements.txt --append --only-write-on-update -o requirements-build.in --allow-binary --no-cache
# pip-compile requirements-build.in --allow-unsafe --generate-hashes

pybuild-deps compile --generate-hashes requirements.txt -o requirements-build.txt
