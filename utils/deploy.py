#!/usr/bin/env python
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter
from collections import namedtuple
from re import fullmatch
from sys import stdin
from sys import stdout


RESOURCE_TEMPLATES = ("insights-inventory-reaper", "insights-inventory-mq-service", "insights-inventory")
TARGETS = {0: "prod", 1: "stage"}
# Note: insights-host-delete resource template uses a different image. Not updated by this script.

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


def _set_name(state, line, match, args):
    return State(match[1], state.target), line


def _reset_target(state, line, match, args):
    return State(state.name, None), line


def _increment_target(state, line, match, args):
    target = 0 if state.target is None else state.target + 1
    return State(state.name, target), line


def _set_image_tag(state, original_line, match, args):
    if state.name in RESOURCE_TEMPLATES and state.target is not None and TARGETS[state.target] in (args.targets or []):
        updated_line = f"{match[1]}{args.promo_code}"
    else:
        updated_line = original_line

    return state, updated_line


def _do_nothing(state, original_line, match, args):
    return state, original_line


LINE_MATCHES = (
    (r"- name: (.+)", _set_name),
    (r"  targets:", _reset_target),
    (r"  - namespace:", _increment_target),
    (r"(      IMAGE_TAG: ).+", _set_image_tag),
)


def _match_line(line):
    for line_match, func in LINE_MATCHES:
        result = fullmatch(line_match, line)
        if result:
            return func, result
    return _do_nothing, None


def _deploy(original_yml, args):
    updated_lines = []
    state = State(None, None)
    for original_line in original_yml.split("\n"):
        func, match = _match_line(original_line)
        state, updated_line = func(state, original_line, match, args)
        updated_lines.append(updated_line)

    return "\n".join(updated_lines)


def main(args, inp, outp):
    original_yml = inp.read()
    updated_yml = _deploy(original_yml, args)
    outp.write(updated_yml)


if __name__ == "__main__":
    parsed_args = _parse_args()
    main(parsed_args, stdin, stdout)
