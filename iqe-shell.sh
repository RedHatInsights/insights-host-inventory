#!/bin/bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/iqe-host-inventory-plugin"
exec uv shell
