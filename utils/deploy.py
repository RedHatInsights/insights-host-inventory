#!/usr/bin/env python
from argparse import ArgumentParser
from sys import stdin
from sys import stdout

from ruamel.yaml import dump
from ruamel.yaml import load
from ruamel.yaml import RoundTripDumper
from ruamel.yaml import RoundTripLoader


RESOURCE_TEMPLATES = ("insights-inventory-reaper", "insights-inventory-mq-service", "insights-inventory")
# Note: insights-host-delete resource template uses a different image. Not updated by this script.


def _parse_args():
    parser = ArgumentParser(description="Add new PROMO_CODE to deploy.yml.")
    parser.add_argument("promo_code", type=str, help="PROMO_CODE to deploy.")
    return parser.parse_args()


def _set_promo_code(original_yml, promo_code):
    updated_yml = {**original_yml, "resourceTemplates": list(original_yml["resourceTemplates"])}
    for rt_i, resource_template in enumerate(updated_yml["resourceTemplates"]):
        if resource_template["name"] in RESOURCE_TEMPLATES:
            updated_yml["resourceTemplates"][rt_i] = {
                **updated_yml["resourceTemplates"][rt_i],
                "targets": list(updated_yml["resourceTemplates"][rt_i]["targets"]),
            }
            for t_i, target in enumerate(updated_yml["resourceTemplates"][rt_i]["targets"]):
                updated_yml["resourceTemplates"][rt_i]["targets"][t_i] = {
                    **updated_yml["resourceTemplates"][rt_i]["targets"][t_i],
                    "parameters": {
                        **updated_yml["resourceTemplates"][rt_i]["targets"][t_i]["parameters"],
                        "IMAGE_TAG": promo_code,
                    },
                }
    return updated_yml


def main(args, inp, outp):
    original_yml = load(inp, RoundTripLoader)
    updated_yml = _set_promo_code(original_yml, args.promo_code)
    dump(updated_yml, outp, RoundTripDumper)


if __name__ == "__main__":
    args = _parse_args()
    main(args, stdin, stdout)
