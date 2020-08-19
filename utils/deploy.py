#!/usr/bin/env python
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter
from collections import namedtuple
from re import fullmatch
from re import sub
from sys import stdin
from sys import stdout


RESOURCE_TEMPLATES = ("insights-inventory-reaper", "insights-inventory-mq-service", "insights-inventory")
TARGETS = {0: "prod", 1: "stage"}
# Note: insights-host-delete resource template uses a different image. Not updated by this script.
IMAGE_TAG_PATTERN = r"(      IMAGE_TAG: ).+"
LINE_MATCHES = (
    (r"- name: (.+)", "name"),
    (r"  targets:", "targets"),
    (r"  - namespace:", "namespace"),
    (IMAGE_TAG_PATTERN, "image_tag"),
)

State = namedtuple("State", ("name", "target"))


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


def _set_promo_code(line, promo_code):
    return sub(IMAGE_TAG_PATTERN, fr"\g<1>{promo_code}", line)


def _match_line(line):
    for line_match, name in LINE_MATCHES:
        result = fullmatch(line_match, line)
        if result:
            return name, result
    return None, None


def _deploy(original_yml, promo_code, targets):
    updated_lines = []
    state = State(None, None)
    for original_line in original_yml.split("\n"):
        updated_line = original_line

        line_type, line_match = _match_line(original_line)
        if line_type == "name":
            state = State(line_match[1], state.target)
        elif line_type == "targets":
            state = State(state.name, None)
        elif line_type == "namespace":
            target = 0 if state.target is None else state.target + 1
            state = State(state.name, target)
        elif (
            line_type == "image_tag"
            and state.name in RESOURCE_TEMPLATES
            and state.target is not None
            and TARGETS[state.target] in targets
        ):
            updated_line = _set_promo_code(original_line, promo_code)

        updated_lines.append(updated_line)

    return "\n".join(updated_lines)


def main(args, inp, outp):
    original_yml = inp.read()
    updated_yml = _deploy(original_yml, args.promo_code, args.targets or [])
    outp.write(updated_yml)


if __name__ == "__main__":
    parsed_args = _parse_args()
    main(parsed_args, stdin, stdout)
