from api.filtering.filtering_common import lookup_operations
from app.exceptions import ValidationException
from app.logging import get_logger

logger = get_logger(__name__)


# build filter based on the operation and OS name and version
def _build_operating_system_version_filter(major, minor, name, operation):
    if minor is None:
        return {"spf_operating_system": {"major": {operation: major}, "name": {"eq": name}}}

    os_filter = {"spf_operating_system": {"major": {"eq": major}, "minor": {operation: minor}, "name": {"eq": name}}}

    if operation != "eq":
        major_operation = operation[0:2]
        os_filter = {
            "OR": [os_filter, {"spf_operating_system": {"major": {major_operation: major}, "name": {"eq": name}}}]
        }

    return os_filter


def _build_filter_from_version_string(os_value, name, operation):
    os_value_split = os_value.split(".")
    major_version = int(os_value_split[0])
    minor_version = int(os_value_split[1]) if len(os_value_split) > 1 else None

    if len(os_value_split) > 2:
        raise ValidationException("operating_system filter can only have a major and minor version.")

    return _build_operating_system_version_filter(major_version, minor_version, name, operation)


def _build_operating_system_version_filter_list(version_list, name, operation):
    os_filters_for_current_name = []
    for version_string in version_list:
        os_filters_for_current_name.append(_build_filter_from_version_string(version_string, name, operation))

    return {"OR": os_filters_for_current_name}


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
                    os_value = version_dict[operation]
                    if isinstance(os_value, list):
                        # Make a list
                        os_filter_for_name = _build_operating_system_version_filter_list(os_value, name, operation)
                    else:
                        os_filter_for_name = _build_filter_from_version_string(os_value, name, operation)

                    os_filters_for_current_name.append(os_filter_for_name)

                else:
                    raise ValidationException(
                        f"Specified operation '{operation}' is not on [operating_system][version] field"
                    )
            os_filters.append({"AND": os_filters_for_current_name})
        else:
            raise ValidationException(f"Incomplete path provided: {operating_system} ")

    return ({"OR": os_filters},)
