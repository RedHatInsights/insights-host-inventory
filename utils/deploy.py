#!/usr/bin/env python
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter
from re import fullmatch
from re import sub
from sys import stdin
from sys import stdout


RESOURCE_TEMPLATES = ("insights-inventory-reaper", "insights-inventory-mq-service", "insights-inventory")
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
    return parser.parse_args()


def _set_promo_code(original_yml, promo_code):
    updated_lines = []
    current_name = None
    for original_line in original_yml.split("\n"):
        name_match = fullmatch(r"- name: (.+)", original_line)
        if name_match:
            current_name = name_match[1]

        if current_name in RESOURCE_TEMPLATES:
            updated_line = sub(r"^(      IMAGE_TAG: ).+$", fr"\g<1>{promo_code}", original_line)
        else:
            updated_line = original_line

        updated_lines.append(updated_line)

    return "\n".join(updated_lines)


def main(args, inp, outp):
    original_yml = inp.read()
    updated_yml = _set_promo_code(original_yml, args.promo_code)
    outp.write(updated_yml)


if __name__ == "__main__":
    parsed_args = _parse_args()
    main(parsed_args, stdin, stdout)
