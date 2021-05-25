from api.filtering.filtering_common import lookup_operations
from app.exceptions import ValidationException
from app.logging import get_logger

logger = get_logger(__name__)


def _build_operating_system_version_filter(major, minor, name, operation):
    # for both lte and lt operation the major operation should be lt
    # so just ignore the 3rd char to get it :)
    # same applies to gte and gt
    major_operation = operation[0:2]

    return {
        "OR": [
            {
                "spf_operating_system": {
                    "major": {"gte": major, "lte": major},  # eq
                    "minor": {operation: minor},
                    "name": {"eq": name},
                }
            },
            {"spf_operating_system": {"major": {major_operation: major}, "name": {"eq": name}}},
        ]
    }


def build_operating_system_filter(field_name, operating_system, field_filter):
    # field name is unused but here because the generic filter builders need it and this has
    # to have the same interface
    os_filters = []

    for name in operating_system:
        if isinstance(operating_system[name], dict) and operating_system[name].get("version"):
            os_filters_for_current_name = []
            version_dict = operating_system[name]["version"]

            # Check that there is an operation at all. No default it wouldn't make sense
            for operation in version_dict:
                if operation in lookup_operations("range"):
                    major_version, *minor_version_list = version_dict[operation].split(".")

                    major_version = int(major_version)
                    minor_version = 0

                    if minor_version_list != []:
                        minor_version = int(minor_version_list[0])

                    os_filters_for_current_name.append(
                        _build_operating_system_version_filter(major_version, minor_version, name, operation)
                    )
                else:
                    raise ValidationException(
                        f"Specified operation '{operation}' is not on [operating_system][version] field"
                    )
            os_filters.append({"AND": os_filters_for_current_name})
        else:
            raise ValidationException(f"Incomplete path provided: {operating_system} ")

    return ({"OR": os_filters},)
