"""
API request validation utilities.

This module contains validation functions for API endpoints,
such as parameter conflict checking and business rule validation.
"""

import flask

from app.logging import get_logger

logger = get_logger(__name__)


def check_group_name_and_id(group_name=None, group_id=None):
    """
    Validate that group_name and group_id filters are not used simultaneously.

    These filters are mutually exclusive because they represent different
    filtering strategies: name-based (potentially ambiguous with Kessel)
    vs ID-based (precise UUID matching).

    Args:
        group_name: Group name filter value (optional)
        group_id: Group ID filter value (optional)

    Raises:
        flask.abort(400): If both filters are provided simultaneously

    Example:
        >>> check_group_name_and_id(group_name="prod")  # OK
        >>> check_group_name_and_id(group_id="uuid")    # OK
        >>> check_group_name_and_id(group_name="prod", group_id="uuid")  # 400 error
    """
    if group_name and group_id:
        logger.warning("Cannot specify both group_name and group_id filters simultaneously.")
        flask.abort(
            400,
            "Cannot use both 'group_name' and 'group_id' filters together. "
            "Please use only one group filter parameter.",
        )
