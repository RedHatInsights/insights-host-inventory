#!/bin/bash
set -e

echo "Setting up IQE test environment..."
echo ""

# Export environment variable for this session
export PIPENV_PIPFILE=Pipfile.iqe

# Install IQE dependencies
echo "Installing IQE dependencies from Pipfile.iqe..."
pipenv install --dev -v

pipenv run pip install --editable ./iqe-host-inventory-plugin

echo ""
echo "✓ IQE environment setup complete!"
echo ""
echo "To activate the IQE environment, run:"
echo "  export PIPENV_PIPFILE=Pipfile.iqe"
echo "  pipenv shell"
echo ""
echo "Or add this to your shell profile for convenience:"
echo "  alias iqe-env='export PIPENV_PIPFILE=Pipfile.iqe && pipenv shell'"
echo "  alias main-env='unset PIPENV_PIPFILE && pipenv shell'"
