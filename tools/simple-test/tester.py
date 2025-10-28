#!/usr/bin/env python

from argparse import ArgumentParser
from json import load as json_load

from jsonschema import validate as jsonschema_validate
from yaml import safe_load as yaml_safe_load


def _parse_args():
    parser = ArgumentParser()
    parser.add_argument("spec_path", type=str, help="YAML schema specification path")
    parser.add_argument("sample_path", type=str, help="JSON document sample path")
    return parser.parse_args()


def main(args):
    with open(args.sample_path) as sample_data, open(args.spec_path) as spec_data:
        sample_dict = json_load(sample_data)
        spec_dict = yaml_safe_load(spec_data)

    schema_dict = {**spec_dict, "$ref": "#/$defs/SystemProfile"}
    jsonschema_validate(instance=sample_dict, schema=schema_dict)


if __name__ == "__main__":
    parsed_args = _parse_args()
    main(parsed_args)
