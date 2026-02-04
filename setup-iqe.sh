#!/usr/bin/env bash
set -e

# Detect OS and re-execute with zsh on macOS (to use zsh pipenv wrapper function)
if [[ "$OSTYPE" == "darwin"* ]] && command -v zsh &> /dev/null; then
    # Check if we're already running in zsh to avoid infinite loop
    if [[ -z "$ZSH_VERSION" ]]; then
        echo "Detected macOS - re-executing with zsh..."
        exec zsh "$0" "$@"
    fi
fi

echo "Setting up IQE test environment..."
echo ""

# Install IQE dependencies
echo "Installing IQE dependencies from Pipfile.iqe..."
PIPENV_PIPFILE=Pipfile.iqe \
PIPENV_CUSTOM_VENV_NAME=insights-host-inventory-iqe \
    pipenv install --dev -v

PIPENV_PIPFILE=Pipfile.iqe \
PIPENV_CUSTOM_VENV_NAME=insights-host-inventory-iqe \
    pipenv run pip install --editable ./iqe-host-inventory-plugin

echo ""
echo "✓ IQE environment setup complete!"
echo ""
echo "Virtual environment created: insights-host-inventory-iqe"
echo ""
echo "To activate the IQE environment, use the alias:"
echo "  iqe-env"
echo ""
echo "Or manually:"
echo "  export PIPENV_PIPFILE=Pipfile.iqe"
echo "  export PIPENV_CUSTOM_VENV_NAME=insights-host-inventory-iqe"
echo "  pipenv shell"
echo ""
if [[ -n "$ZSH_VERSION" ]]; then
    echo "Note: The 'iqe-env' and 'main-env' aliases should be in your ~/.zshrc"
else
    echo "Note: The 'iqe-env' and 'main-env' aliases should be in your ~/.bashrc or ~/.bash_profile"
fi
