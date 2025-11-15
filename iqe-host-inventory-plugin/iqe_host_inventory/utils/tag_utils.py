from __future__ import annotations

from collections.abc import Callable
from typing import cast
from urllib.parse import quote

from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import gen_tag_with_parameters
from iqe_host_inventory_api import ActiveTag
from iqe_host_inventory_api import StructuredTag


def convert_tag_to_string(tag_structure: dict[str, str] | object, url_encode: bool = False) -> str:
    """Converts tag from structured representation to string representation."""
    if not isinstance(tag_structure, dict):
        raise ValueError(
            f"Wrong tag representation provided, expected dict, received {tag_structure}"
        )
    encode: Callable[[str], str] = cast(Callable[[str], str], quote if url_encode else str)

    namespace = tag_structure.get("namespace")
    key = tag_structure["key"]
    value = tag_structure.get("value")
    tag_string = encode(key)
    if namespace:
        tag_string = f"{encode(namespace)}/{tag_string}"
    if value:  # empty string should encode as missing value as of now
        tag_string = f"{tag_string}={encode(value)}"
    if not namespace and "/" in key:
        tag_string = f"/{tag_string}"
    return tag_string


def convert_tag_from_nested_to_structured(tag_nested: dict) -> list[TagDict]:
    if not isinstance(tag_nested, dict):
        raise ValueError(
            f"Wrong tag representation provided, expected dict, received {tag_nested}"
        )
    tag_structured = []
    for namespace, keys in tag_nested.items():
        namespace = None if namespace == "" else namespace
        for key, values in keys.items():
            if isinstance(values, list) and len(values) > 0:
                for value in values:
                    value = None if value == "" else value
                    tag_structured.append(
                        gen_tag_with_parameters(namespace=namespace, key=key, value=value)
                    )
            else:
                tag_structured.append(
                    gen_tag_with_parameters(namespace=namespace, key=key, value=None)
                )

    return tag_structured


def sort_tags(tags: list):
    return {
        tuple(sorted(tag.items() if isinstance(tag, dict) else tag.to_dict().items()))
        for tag in tags
    }


def convert_tag_to_dict(
    tag: TagDict | StructuredTag | ActiveTag | dict,
) -> TagDict | dict[str, str | None]:
    """
    Expects tag in one of these types: TagDict, StructuredTag, ActiveTag, dict.
    If the tag is of type 'dict', the expected format is one of:
    - {"key": <key>, "namespace": <namespace>, "value": <value>}
    - {"tag": {"key": <key>, "namespace": <namespace>, "value": <value>}, "count": <count>}

    Returns tag as dict in this format:
    - {"key": <key>, "namespace": <namespace>, "value": <value>}
    """
    if isinstance(tag, StructuredTag):
        return tag.to_dict()
    if isinstance(tag, ActiveTag):
        return tag.tag.to_dict()
    if isinstance(tag, dict):  # TagDict object is also instance of dict
        if "key" in tag:
            return tag
        if "tag" in tag:
            # TODO: Fix mypy confusion, it thinks this is TagDict, but that would be returned above
            return tag["tag"]  # type: ignore
        raise ValueError(f"Provided tag dictionary is not formatted correctly: {tag}")
    raise TypeError(f"Provided tag has unexpected type: {type(tag)}")


def assert_tags_found(
    expected_tags: list[TagDict] | list[StructuredTag],
    response_tags: list[dict] | list[ActiveTag] | list[TagDict],
    *,
    check_api_response_count: bool = True,
) -> None:
    string_expected_tags = {
        convert_tag_to_string(convert_tag_to_dict(tag)) for tag in expected_tags
    }
    string_response_tags = {
        convert_tag_to_string(convert_tag_to_dict(tag)) for tag in response_tags
    }
    found_tags = string_expected_tags.intersection(string_response_tags)
    assert found_tags == string_expected_tags
    if check_api_response_count:
        for tag in response_tags:
            if convert_tag_to_string(convert_tag_to_dict(tag)) in found_tags:
                assert (tag["count"] if isinstance(tag, dict) else tag.count) == 1  # type: ignore


def assert_tags_not_found(
    not_expected_tags: list[TagDict] | list[StructuredTag],
    response_tags: list[dict] | list[ActiveTag],
) -> None:
    string_not_expected_tags = {
        convert_tag_to_string(convert_tag_to_dict(tag)) for tag in not_expected_tags
    }
    for tag in response_tags:
        assert convert_tag_to_string(convert_tag_to_dict(tag)) not in string_not_expected_tags


def normalize_tags(tags: list[dict]):
    tags = list(tags)
    for tag in tags:
        if "namespace" not in tag:
            tag["namespace"] = None
        if "value" not in tag:
            tag["value"] = None
    return tags
