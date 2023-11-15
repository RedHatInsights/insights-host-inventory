#!/usr/bin/env python
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter
from collections import namedtuple
from functools import partial
from functools import reduce
from re import fullmatch
from sys import stdin
from sys import stdout


RESOURCE_TEMPLATES = ("insights-inventory-reaper", "insights-inventory-mq-service", "insights-inventory")
TARGETS = {0: "prod", 1: "stage"}
# Note: insights-host-delete resource template uses a different image. Not updated by this script.


Current = namedtuple("Current", ("name", "target"))


def _parse_args():
    parser = ArgumentParser(
        description="""Replaces IMAGE_TAG in the App Interface Host Inventory deploy.yml with
the provided PROMO_CODE. Reads from stdin, writes to stdout.
Possible usage: pipenv run python3 utils/deploy.py < path/to/deploy.yml | sponge path/to/deploy.yml
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


def _set_name(name, target, match, args):
    return match[1], target, match[0]


def _reset_target(name, target, match, args):
    return name, None, match[0]


def _increment_target(name, target, match, args):
    target = 0 if target is None else target + 1
    return name, target, match[0]


def _set_image_tag(name, target, match, args):
    if name in RESOURCE_TEMPLATES and target is not None and TARGETS[target] in (args.targets or []):
        promo_code = args.promo_code
    else:
        promo_code = match[2]

    return name, target, f"{match[1]}{promo_code}"


def _do_nothing(name, target, match, args):
    return name, target, match[0]


LINE_MATCHES = (
    (r"- name: (.+)", _set_name),
    (r"  targets:", _reset_target),
    (r"  - namespace:", _increment_target),
    (r"(      IMAGE_TAG: )(.+)", _set_image_tag),
    (r".*", _do_nothing),
)


def _match_line(line):
    for line_match, func in LINE_MATCHES:
        result = fullmatch(line_match, line)
        if result:
            return func, result
    raise RuntimeError


def _process_line(args, state, original_line):
    current, processed_lines = state
    func, match = _match_line(original_line)
    name, target, processed_line = func(current.name, current.target, match, args)
    return Current(name, target), processed_lines + [processed_line]


def _deploy(original_yml, args):
    process_line = partial(_process_line, args)
    original_lines = original_yml.split("\n")
    initial = (Current(None, None), [])
    _, processed_lines = reduce(process_line, original_lines, initial)
    return "\n".join(processed_lines)


def main(args, inp, outp):
    original_yml = inp.read()
    updated_yml = _deploy(original_yml, args)
    outp.write(updated_yml)


if __name__ == "__main__":
    parsed_args = _parse_args()
    main(parsed_args, stdin, stdout)
