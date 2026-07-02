#!/usr/bin/env python3
"""Return a pip-compatible uv version specifier from pyproject.toml."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path

_OPERATOR_PREFIX = re.compile(r"^[<>=!~]")


def _with_operator(specifier: str) -> str:
    specifier = specifier.strip()
    if _OPERATOR_PREFIX.match(specifier):
        return specifier
    return f"=={specifier}"


def get_pip_specifier(pyproject: Path, *, build_pin: bool) -> str:
    if build_pin:
        pin_file = pyproject.parent / "uv-build-version"
        if not pin_file.is_file():
            raise SystemExit(f"Missing build pin file: {pin_file}")
        return _with_operator(pin_file.read_text())

    data = tomllib.loads(pyproject.read_text())
    return _with_operator(data["tool"]["uv"]["required-version"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pyproject",
        nargs="?",
        default="pyproject.toml",
        type=Path,
        help="Path to pyproject.toml (default: pyproject.toml)",
    )
    parser.add_argument(
        "--build-pin",
        action="store_true",
        help="Install the exact uv version from uv-build-version (for reproducible builds).",
    )
    args = parser.parse_args()
    print(get_pip_specifier(args.pyproject, build_pin=args.build_pin))


if __name__ == "__main__":
    main()
