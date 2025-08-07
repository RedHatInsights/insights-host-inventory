#!/bin/bash


pip3 install pip-tools pybuild-deps
pip3 install "pip<25"
cd /var/tmp

pip-compile requirements-build.in --allow-unsafe --generate-hashes
pip-compile requirements-extras.in --allow-unsafe --generate-hashes


# pybuild-deps compile --generate-hashes requirements.txt -o requirements-build.txt
# pip-compile requirements-build.in --allow-unsafe --generate-hashes -o requirements-extras.txt
