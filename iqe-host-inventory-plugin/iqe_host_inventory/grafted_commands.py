from __future__ import annotations

import contextlib
import datetime as dt
import gzip
import io
import logging
import sys
import time
from collections.abc import Generator
from datetime import datetime
from typing import Any

import click
import requests.exceptions
from iqe.base.application import Application

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.user_fixtures import require_user
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.datagen_utils import create_system_profile_errata
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.upload_utils import build_host_archive

PARENT_LOGGER = logging.getLogger()
LOGGER = logging.getLogger("host_inventory_group")


@click.group("host_inventory")
def host_inventory_group():
    pass


def get_older_hosts(  # NOQA: C901
    host_inventory: ApplicationHostInventory,
    unit: str,
    interval: int,
    retries: int,
    excludes: tuple[str],
) -> dict[int, str]:
    now = datetime.now(dt.UTC)
    total_url_len = len(host_inventory.apis.hosts.api_client.configuration.host)
    total_requests: dict[int, Any] = {}
    request_key = 0
    page_info = host_inventory.apis.hosts.get_host_pagination_info(per_page=100)

    for page in page_info.pages:
        for i in range(retries):
            try:
                hosts = host_inventory.apis.hosts.get_hosts_response(per_page=100, page=page)
                break  # 200 response
            except AssertionError as e:
                if any("status 500" in i for i in e.args):
                    time.sleep(5)  # Give the server a little time, it may have crashed.
                    LOGGER.warning(f"Getting page {page} failed, retry #{i}")
                    continue
                else:
                    raise
            except requests.exceptions.ConnectionError:
                time.sleep(5)  # Give the server a little time, it may have crashed.
                LOGGER.warning(f"Getting page {page} failed, retry #{i}")
                continue

        for host in hosts.results:
            host_id = host.id
            host_fqdn = host.fqdn

            if host_id in excludes or host_fqdn in excludes:
                LOGGER.info(f"Excluding: {host_fqdn}/{host_id}")
                continue

            delta = now - host.updated
            total_url_len = total_url_len + len(f",{host_id}")

            if getattr(delta, unit) > interval:
                # total_url_len refers to the request URL's maximum length
                if total_url_len > 2000:
                    total_url_len = len(
                        host_inventory.apis.hosts.api_client.configuration.host
                    ) + len(host_id)
                    request_key += 1

                if request_key not in total_requests:
                    host_str = host_id
                else:
                    host_str = f"{total_requests[request_key]},{host_id}"

                total_requests[request_key] = host_str

    return total_requests


def delete_hosts(
    host_inventory: ApplicationHostInventory, old_hosts: dict[int, str], dry_run: bool = False
):
    """
    Takes a list of hosts and sends a comma delimited DELETE
    """
    if dry_run:
        return

    for hosts in old_hosts.values():
        # They are now doomed
        hosts_split = hosts.split(",")
        host_inventory.apis.hosts.delete_by_id(hosts_split)


@host_inventory_group.command("cleanup")
@click.option("-y", "--yes", help="Skip the interactive prompt.", is_flag=True)
@click.option(
    "-n",
    "--dry-run",
    help="Skip the destruction, and print instead.",
    is_flag=True,
)
@click.option(
    "-u",
    "--unit",
    help="Specify the unit of time instead of default days",
    default="days",
    type=click.Choice(["days", "seconds", "microseconds"]),
)
@click.option(
    "-i",
    "--interval",
    help="Specify the interval for the time unit instead of the default 7",
    default=7,
)
@click.option(
    "-r",
    "--retries",
    help="Specify the number of retries instead of the default 5",
    default=5,
)
@click.option(
    "-v",
    "--verbose",
    help="Run cleanup in info (-v) or debug (-vv or more)",
    count=True,
)
@click.option(
    "-e",
    "--exclude",
    help="Exclude these hosts from cleanup (hostname/uuid)",
    multiple=True,
)
@click.option(
    "--user",
    help="C.R.C user from iqe-core or local config. (Default: insights_qa)",
    default="insights_qa",
)
@click.pass_obj
def cleanup(obj, yes, dry_run, unit, interval, retries, verbose, exclude, user):
    """
    Runs a cleanup against the inventory for older hosts.
    """
    with _app_with_maybe_user(obj.primary_application, user) as app:
        LOGGER = logging.getLogger("host_inventory_group.cleanup")
        host_inventory = app.host_inventory

        # Always exclude pit-med-03.lab.bos.redhat.com/4b503f2c-6f4b-44cb-a9df-a9cec5ba7bf9
        exclude = (*exclude, "pit-med-03.lab.bos.redhat.com")

        if verbose == 1:
            log_level = logging.INFO
        elif verbose > 1:
            log_level = logging.DEBUG
        else:
            log_level = logging.ERROR

        logging.basicConfig(level=log_level)  # Setup our root logger for the CLI
        PARENT_LOGGER.setLevel(log_level)
        LOGGER.setLevel(log_level)

        LOGGER.info(host_inventory.apis.hosts.api_client.configuration.host)

        LOGGER.info(f"Getting hosts older than {interval} {unit}...")
        old_hosts = get_older_hosts(
            host_inventory,
            unit=unit,
            interval=interval,
            retries=retries,
            excludes=exclude,
        )

        if len(old_hosts) == 0:
            LOGGER.error("No old hosts found")
            sys.exit(0)

        old_hosts_to_delete = f"\nOld hosts to delete: {''.join(h for h in old_hosts.values())}"
        if log_level == logging.ERROR:
            print(old_hosts_to_delete)
        else:
            LOGGER.info(old_hosts_to_delete)

        if not yes and not dry_run and not click.confirm("Delete these hosts?"):
            LOGGER.error("Not proceeding.")
            sys.exit(0)

        LOGGER.info("Deleting..." if not dry_run else "These hosts would have been deleted.")
        delete_hosts(host_inventory, old_hosts, dry_run=dry_run)


@contextlib.contextmanager
def _app_with_maybe_user(
    app: Application, given_user: str | None = None
) -> Generator[Application]:
    if given_user is None:
        yield app
    else:
        user = require_user(app, given_user)
        with app.copy_using(user=user) as new_app:
            yield new_app


@host_inventory_group.command()
@click.option("-n", "--number", help="Number of hosts to create", default=51)
@click.option(
    "--user",
    help="C.R.C user from iqe-core or local config. (Default: insights_qa)",
    default="insights_qa",
)
@click.option(
    "--display-name-prefix", help="Display name prefix for hosts", default="rhiqe.example"
)
@click.option(
    "--store",
    help="Path for storing archives instead of uploading them",
    default=None,
    type=click.Path(file_okay=False, exists=True),
)
@click.option("--base-archive", help="Name of the base archive", default=None)
@click.option("--archive-repo", help="IQE plugin with the archive", default=None)
@click.pass_obj
def create_hosts(obj, number, user, display_name_prefix, store, base_archive, archive_repo):
    """
    Creates hosts by uploading insights archives to ingress
    """
    base_hostname = generate_display_name(panic_prevention=display_name_prefix)

    archives = [
        build_host_archive(
            display_name=f"{base_hostname}.test_{n:02}",
            base_archive=base_archive,
            archive_repo=archive_repo,
        )
        for n in range(number)
    ]

    if store is None:
        with _app_with_maybe_user(obj.primary_application, user) as app:
            click.echo(f"Uploading {number} insights archives to ingress")
            app.host_inventory.upload.async_upload_archives(archives)
            click.echo("All archives were successfully uploaded")
    else:
        click.echo(f"Creating {number} new insights archives in {store}")
        for index, archive in enumerate(archives):
            assert isinstance(archive.new_in_memory_file, io.BytesIO)
            with gzip.open(f"{store}/new.{index}.tgz", "wb") as output_file:
                output_file.write(archive.new_in_memory_file.getvalue())
        click.echo("All archives were successfully created")


@host_inventory_group.command()
@click.option("-n", "--number", help="Number of hosts to create", default=1)
@click.option(
    "--user",
    help="C.R.C user from iqe-core or local config. (Default: primary_user)",
    default="primary_user",
)
@click.option(
    "--display-name-prefix", help="Display name prefix for hosts", default="rhiqe.example"
)
@click.option(
    "--reporter", help="Simulate host messages from this reporter", default="iqe-hbi-plugin"
)
@click.option("--timeout", help="Timeout for searching events for created hosts", default=30)
@click.option("--wait-for-events", help="Wait for events created by HBI", default=True)
@click.pass_obj
def create_hosts_kafka(obj, number, user, display_name_prefix, reporter, timeout, wait_for_events):
    """
    Creates hosts by sending kafka messages to HBI.
    Can be used only from inside the cluster, for example in ephemeral envs.
    """
    base_display_name = generate_display_name(panic_prevention=display_name_prefix)

    with _app_with_maybe_user(obj.primary_application, user) as app:
        host_inventory: ApplicationHostInventory = app.host_inventory

        hosts_data = []
        for i in range(number):
            host_data = host_inventory.datagen.create_host_data_with_tags(
                display_name=f"{base_display_name}.{i:02}", reporter=reporter
            )
            if reporter == "errata-notifications":
                host_data["system_profile"] = create_system_profile_errata()
                host_data.pop("insights_id", None)
            hosts_data.append(host_data)
        insights_ids = [host["insights_id"] for host in hosts_data]

        click.echo(f"Producing {number} kafka messages")
        host_inventory.kafka.produce_host_create_messages(hosts_data, flush=True)

        if wait_for_events:
            click.echo("Searching for events produced by HBI for created hosts")
            created_hosts = host_inventory.kafka.wait_for_filtered_host_messages(
                HostWrapper.insights_id, insights_ids, timeout=timeout
            )
            click.echo("Found events for all hosts. Hosts IDs:")
            for host in created_hosts:
                click.echo(f"{host.host.display_name}: {host.host.id}")
