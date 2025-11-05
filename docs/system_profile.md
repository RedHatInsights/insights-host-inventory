# Cloud Platform Inventory Schemas #

System Profile is a subset of data stored in Inventory.
This document provides information regarding changes to the System Profile schema.

## Technical Details ##

System Profile specification is written in YAML containing an [OpenAPI 3.0](https://swagger.io/specification/) definition schema. All entities are under _$def_ root key, internal references (_$ref_) use relative referencing (_#/$def/entity_).

Document version is reflected in the filename (_v1.yaml_) and under _$version_ root key. _$id_ is a file name used in
the Host Inventory.

## Contributing ##

When contributing a new field to the system_profile schema, please ensure you complete the following steps:

1. Add the new field to the appropriate model
    - [System Profile Static](../app/models/system_profile_static.py) or [Dynamic](../app/models/system_profile_dynamic.py),
    based on how often the field is expected to be updated.
2. Add the field to the [system_profile schema](../swagger/system_profile.spec.yaml)
    1. Annotate the field
        - Add an example of the value(s) you expect to receive using the `example` keyword. For string fields, provide at least 2 unique examples.
        - Add a description of the field. If the field should support `range` or `wildcard` operations when queried against, note that here.
    2. Add filtering flags
        - If the field should support wildcard operations in filtering, add `x-wildcard: true`. Defaults to `false` otherwise.
    3. Validate the field
        - The field should have the strictest possible validation rules applied to it.
    4. Add positive and negative test examples
        - Add examples of valid/invalid values in `tests/utils/valids` and `tests/utils/invalids` respectively.

## Process For Merging Schema Changes ##

1. Once a pull request is opened to update a pre-existing field, the dippy-bot will validate the changes, produce a report similar to to the following, and post it in the pull request thread.

    | Reporters | Result | Count |
    | --- | --- | --- |
    | ingress | Pass | 10 |
    | ingress | Fail | 2 |
    | puptoo | Pass | 37 |
    | puptoo | Fail | 42 |

3. If the report seems satisfactory and there are no more concerns, a repository maintainer will merge the PR.

4. In the event that the report is unsatisfactory (e.g. it shows a high number of failures from one or multiple reporters), the PR owner must coordinate with the repository maintainers and the stakeholders from the reporter(s) that show failures. Together, they must decide whether to change the PR or to update the reporter(s).

5. If the pull request only adds new fields there is no need to generate a report since the database will not contain values to compare against for the new fields. A repository maintainer will help in getting consensus with the schema [Stakeholders](#stakeholders) before merging the PR.

### Stakeholders ###

- RHSM - # find out who is the point of contact now
- Yupana - [Jaylin Zhou](https://github.com/koalakangaroo), [Xiangce Liu](https://github.com/xiangce)
- Puptoo - [Jaylin Zhou](https://github.com/koalakangaroo), [Xiangce Liu](https://github.com/xiangce)
- BU - [Jerome Marc](https://github.com/jeromemarc)

[OpenAPI 3.0]: https://swagger.io/specification/
