import logging

from enum import Enum

from app.exceptions import InventoryException
from app.logging import get_logger
from app.models import db, Host, HostSchema

# FIXME:  rename this
AddHostResults = Enum("AddHostResults", ["created", "updated"])


logger = get_logger(__name__)


def add_host(host):
    """
    Add or update a host

    Required parameters:
     - at least one of the canonical facts fields is required
     - account number
    """
    validated_input_host_dict = HostSchema(strict=True).load(host)

    input_host = Host.from_json(validated_input_host_dict.data)

    existing_host = find_existing_host(input_host.account,
                                       input_host.canonical_facts)

    if existing_host:
        return update_existing_host(existing_host, input_host)
    else:
        return create_new_host(input_host)


#@metrics.host_dedup_processing_time.time()
def find_existing_host(account_number, canonical_facts):
    existing_host = None
    insights_id = canonical_facts.get("insights_id", None)

    if insights_id:
        # The insights_id is the most important canonical fact.  If there
        # is a matching insights_id, then update that host.
        existing_host = find_host_by_insights_id(account_number, insights_id)

    if not existing_host:
        existing_host = find_host_by_canonical_facts(account_number,
                                                     canonical_facts)

    return existing_host


def find_host_by_insights_id(account_number, insights_id):
    existing_host = Host.query.filter(
            (Host.account == account_number)
            & (Host.canonical_facts["insights_id"].astext == insights_id)
        ).first()

    if existing_host:
        logger.debug("Found existing host using id match: %s", existing_host)

    return existing_host


def _canonical_facts_host_query(account_number, canonical_facts):
    return Host.query.filter(
        (Host.account == account_number)
        & (
            Host.canonical_facts.comparator.contains(canonical_facts)
            | Host.canonical_facts.comparator.contained_by(canonical_facts)
        )
    )


def find_host_by_canonical_facts(account_number, canonical_facts):
    """
    Returns first match for a host containing given canonical facts
    """
    logger.debug("find_host_by_canonical_facts(%s)", canonical_facts)

    host = _canonical_facts_host_query(account_number, canonical_facts).first()

    if host:
        logger.debug("Found existing host using canonical_fact match: %s", host)

    return host


#@metrics.new_host_commit_processing_time.time()
def create_new_host(input_host):
    logger.debug("Creating a new host")
    input_host.save()
    db.session.commit()
    #metrics.create_host_count.inc()
    logger.debug("Created host:%s" % input_host)
    return input_host.to_json(), AddHostResults.created


#@metrics.update_host_commit_processing_time.time()
def update_existing_host(existing_host, input_host):
    logger.debug("Updating an existing host")
    existing_host.update(input_host)
    db.session.commit()
    #metrics.update_host_count.inc()
    logger.debug("Updated host:%s" % existing_host)
    return existing_host.to_json(), AddHostResults.updated

