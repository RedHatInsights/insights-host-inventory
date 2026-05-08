#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$ROOT/iqe-host-inventory-plugin"

echo "Setting up IQE test environment..."
echo ""

echo "Installing IQE dependencies from iqe-host-inventory-plugin (uv) ..."
(cd "$PLUGIN" && uv sync)

echo ""
echo "✓ IQE environment setup complete!"
echo ""
echo "IQE uses the plugin virtual environment. Examples:"
echo "  cd iqe-host-inventory-plugin && uv run iqe --help"
echo "  cd iqe-host-inventory-plugin && uv shell"
echo ""
echo "To refresh the lockfile after dependency changes (VPN + Red Hat CA required for iqe-core):"
echo "  cd iqe-host-inventory-plugin && uv lock --python 3.12"
