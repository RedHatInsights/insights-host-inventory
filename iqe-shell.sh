#!/bin/bash
# Quick helper to activate IQE environment
export PIPENV_PIPFILE=Pipfile.iqe
exec pipenv shell
