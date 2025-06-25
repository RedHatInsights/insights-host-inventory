#!/bin/bash


pip3 install pip-tools pybuild-deps
pip3 install "pip<25"
cd /var/tmp

pip-compile requirements-build.in --allow-unsafe --generate-hashes
