from __future__ import annotations

import math
import re
import time
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from selenium.common import exceptions

from iqe_host_inventory.utils.datagen_utils import generate_uuid

UNIQUE_UI_ID = "hbi-ui"
CENTOS_LABEL = "Convert system to RHEL"

UI_SYSTEM_PROFILE_FIELDS = [
    "bootc_status",
    "sap_sids",
    "cpu_flags",
    "system_purpose",
    "number_of_cpus",
    "number_of_sockets",
    "cores_per_socket",
    "system_memory_bytes",
    "kernel_modules",
    "os_kernel_version",
    "operating_system",
    "arch",
    "last_boot_time",
    "bios_vendor",
    "bios_version",
    "bios_release_date",
    "network_interfaces",
    "infrastructure_type",
    "infrastructure_vendor",
    "installed_packages",
    "running_processes",
    "enabled_services",
    "yum_repos",
    "rhc_client_id",
    "system_update_method",
    "public_ipv4_addresses",
    "public_dns",
    "bootc_status",
]

# Helper constants to generate Inventory dashboard related content
URL_FILTERS = {
    "insights_systems": "source=puptoo",
    "stale_systems": "status=stale&source=puptoo",
    "systems_to_remove": "status=stale_warning&source=puptoo",
}

DASHBOARD_FILTERS = {
    "insights_systems": ["insights-client"],
    "stale_systems": ["insights-client", "Stale"],
    "systems_to_remove": ["insights-client", "Stale warning"],
}

LAST_SEEN_FILTERS = [
    "Within the last 24 hours",
    "More than 1 day ago",
    "More than 7 days ago",
    "More than 15 days ago",
    "More than 30 days ago",
    "Custom",
]

FILTER_DATETIME_FORMAT = {
    "Within the last 24 hours": datetime.utcnow() - timedelta(hours=24),
    "More than 1 day ago": datetime.utcnow() - timedelta(days=1),
    "More than 7 days ago": datetime.utcnow() - timedelta(days=7),
    "More than 15 days ago": datetime.utcnow() - timedelta(days=15),
    "More than 30 days ago": datetime.utcnow() - timedelta(days=30),
}


def get_last_seen_column_values(view, first_row=False, workspace_date=False):
    MAX_TRIES = 10
    # Regex for the date pattern
    pattern = re.compile(r"\d{2} \w{3} \d{4} \d{2}:\d{2} \w{3}")
    data = []
    tries = 0
    # Sometimes grabbing the hover text is flaky, so waiting and retrying a few times here
    for row in view.table.rows():
        while tries < MAX_TRIES:
            try:
                if workspace_date:
                    data.append(re.search(pattern, row.last_modified.widget.text).group(0))
                else:
                    data.append(re.search(pattern, row.last_seen.widget.text).group(0))
                break
            except AttributeError:
                view.browser.move_to_element(row.name)
                time.sleep(1)
            except exceptions.StaleElementReferenceException:
                if workspace_date:
                    view.browser.move_to_element(row.last_modified)
                else:
                    view.browser.move_to_element(row.last_seen)
            tries += 1
        if first_row:
            view.browser.move_to_element(row.name)
            time.sleep(1)
            break
        tries = 0
    return data


def date_to_str(date: datetime):
    return date.strftime("%Y-%m-%d")


def assert_last_seen_datetime(
    filter: str,
    filtered_date: str,
    updated_start: datetime | None = None,
    updated_end: datetime | None = None,
):
    date = datetime.strptime(filtered_date, "%d %b %Y %H:%M %Z")
    if filter == "Custom":
        if updated_start is not None and updated_end is not None:
            assert updated_start <= date <= updated_end
        elif updated_start:
            assert updated_start <= date
        elif updated_end:
            assert date <= updated_end
    else:
        if filter == "Within the last 24 hours":
            assert FILTER_DATETIME_FORMAT[filter] <= date
        else:
            assert date <= FILTER_DATETIME_FORMAT[filter]


def get_tags_from_tags_modal(view, expected_tags: int) -> list[dict]:
    PER_PAGE = 10
    modal_tags: list[dict] = []
    tmp_count = expected_tags
    while tmp_count > 0:
        modal_tags.extend(view.table.read())
        if tmp_count > PER_PAGE:
            view.top_paginator.next_page()
        tmp_count -= PER_PAGE

    return modal_tags


def format_bytes(bytes):
    """Convert byte size"""
    sizes = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    try:
        index = math.floor(math.log(bytes) / math.log(1024))
        return f"{round(bytes / (1024**index), 2)} {sizes[index]}"
    except (ValueError, TypeError):
        return "0 B"


def get_status_indicator_based_on_stale_data(stale_data):
    current_date = datetime.now(UTC)
    status_indicator: str = ""

    if current_date < stale_data["Stale"] and current_date >= stale_data["Created"]:
        # no indicator is displayed for fresh system
        status_indicator = status_indicator
    elif current_date < stale_data["Stale_warning"]:
        # yellow indicator is displayed for stale system
        status_indicator = "warning"
    else:
        # red indicator is displayed for stale_warning system
        status_indicator = "danger"

    return status_indicator


def convert_system_profile_when_not_available(system_profile):
    """Convert system_profile data to match UI display system's information
    when data is missing (UI is displaying 'Not available')"""
    for field in UI_SYSTEM_PROFILE_FIELDS:
        if system_profile.get(field) is None:
            system_profile[field] = "Not available"

    return system_profile


def generate_workspace_name(panic_prevention: str = "hbi") -> str:
    """Function is needed for frontend test - UI doesn't allow
    to create workspace with dot character"""
    return f"{panic_prevention}_{generate_uuid()}"
