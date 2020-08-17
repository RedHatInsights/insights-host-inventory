#!/usr/bin/env python
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter
from re import fullmatch
from re import sub
from sys import stdin
from sys import stdout


RESOURCE_TEMPLATES = ("insights-inventory-reaper", "insights-inventory-mq-service", "insights-inventory")
TARGETS = {0: "prod", 1: "stage"}
# Note: insights-host-delete resource template uses a different image. Not updated by this script.


def _parse_args():
    parser = ArgumentParser(
        description="""Replaces IMAGE_TAG in the App Interface Host Inventory deploy.yml with
the provided PROMO_CODE. Reads from stdin, writes to stdout.
Possible usage: pipenv run python utils/deploy.py < path/to/deploy.yml | sponge path/to/deploy.yml
sponge is part of moreutils""",
        formatter_class=RawTextHelpFormatter,
    )
    parser.add_argument("promo_code", type=str, help="PROMO_CODE to deploy.")
    parser.add_argument(
        "-s", "--stage", action="append_const", const="stage", dest="targets", help="Deploy to stage environment."
    )
    parser.add_argument(
        "-p", "--prod", action="append_const", const="prod", dest="targets", help="Deploy to prod environment."
    )
    return parser.parse_args()


def _set_promo_code(original_yml, promo_code, targets):
    updated_lines = []
    current_name = None
    current_target = None
    for original_line in original_yml.split("\n"):
        name_match = fullmatch(r"- name: (.+)", original_line)
        if name_match:
            current_name = name_match[1]

        targets_match = fullmatch(r"  targets:", original_line)
        if targets_match:
            current_target = None

        namespace_match = fullmatch(r"  - namespace:", original_line)
        if namespace_match:
            current_target = 0 if current_target is None else current_target + 1

        if current_name in RESOURCE_TEMPLATES and current_target is not None and TARGETS[current_target] in targets:
            updated_line = sub(r"^(      IMAGE_TAG: ).+$", fr"\g<1>{promo_code}", original_line)
        else:
            updated_line = original_line

        updated_lines.append(updated_line)

    return "\n".join(updated_lines)


def main(args, inp, outp):
    original_yml = inp.read()
    updated_yml = _set_promo_code(original_yml, args.promo_code, args.targets or [])
    outp.write(updated_yml)


if __name__ == "__main__":
    parsed_args = _parse_args()
    main(parsed_args, stdin, stdout)
