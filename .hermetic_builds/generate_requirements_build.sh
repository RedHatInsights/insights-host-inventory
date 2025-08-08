#!/bin/bash

hermetic_builds_dir=${1:-".hermetic_builds"}

pip3 install pip-tools pybuild-deps
pip3 install "pip<25"

pip-compile $hermetic_builds_dir/requirements-build.in --allow-unsafe --generate-hashes
pip-compile $hermetic_builds_dir/requirements-extras.in --allow-unsafe --generate-hashes


# pybuild-deps compile --generate-hashes requirements.txt -o requirements-build.txt
# pip-compile requirements-build.in --allow-unsafe --generate-hashes -o requirements-extras.txt
