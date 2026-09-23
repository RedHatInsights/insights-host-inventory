from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import request
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import load_only

from app.auth.identity import from_auth_header
from app.models import Host
from app.models import db
from lib.db import session_guard

tags_bp = Blueprint("tags", __name__)


def combine_tags(input_list, existing_dict=None):
    """
    Reformats a list of dictionaries into a nested dictionary structure, additively merged
    on top of existing_dict. Never mutates existing_dict.

    Args:
        input_list: List of dictionaries with 'namespace', 'key', and 'value' fields
        existing_dict: Optional existing dictionary to merge on top of (default: None)

    Returns:
        A dict in the format {namespace: {key: [value, ...]}}. If input_list doesn't
        change anything, returns existing_dict itself, unmodified. Otherwise returns a
        new dict: any touched namespace/key gets fresh containers, while every untouched
        namespace/key is shared by reference with existing_dict, never copied or mutated.
    """
    result = existing_dict or {}

    # Process each item in the input list
    for item in input_list:
        namespace = item.get("namespace")
        key = item.get("key")
        value = item.get("value")

        # Skip invalid entries
        if not all([namespace, key, value]):
            continue

        # Check membership against the existing list before copying anything -
        # a true no-op (the common case) makes zero copies.
        existing_values = result.get(namespace, {}).get(key, [])
        if value in existing_values:
            continue

        ns_tags = dict(result.get(namespace, {}))
        ns_tags[key] = [*existing_values, value]

        result = dict(result)
        result[namespace] = ns_tags

    return result


def update_host_tags(session, host, tags):
    try:
        current_tags = combine_tags(tags, host.tags)
        # identity check first: dict == doesn't short-circuit on it, and combine_tags
        # returns host.tags itself when nothing changed.
        if current_tags is host.tags or current_tags == host.tags:
            return True
        host._update_tags(current_tags)
        session.add(host)
        return True
    except Exception as e:
        current_app.logger.error(f"Error updating host {host.id}: {str(e)}")
        return False


def process_host_batch(session, identity, batch_ids, tags):
    hosts = (
        session.query(Host)
        .options(load_only(Host.id, Host.tags))
        .filter(and_(Host.org_id == identity.org_id, Host.id.in_(batch_ids)))
        .all()
    )
    found_host_ids = {str(host.id) for host in hosts}
    not_found = [hid for hid in batch_ids if str(hid) not in found_host_ids]

    processed = 0
    for host in hosts:
        if update_host_tags(session, host, tags):
            processed += 1
    return processed, not_found


@tags_bp.route("/tags", methods=["POST"])
def bulk_tag_hosts():
    """
    Supports POST endpoint /tags to enable the bulk addition of tags to hosts.
    Expects a body payload of tags and host_id_list in order to update the list of hosts with the given list of tags.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        identity = from_auth_header(request.headers["x-rh-identity"])
        if not identity.org_id:
            return jsonify({"error": "No identity provided"}), 401

        tags = data.get("tags", [])
        host_id_list = data.get("host_id_list", [])

        # Validate required fields
        if not tags:
            return jsonify({"error": "Missing required field: tags"}), 400
        if not host_id_list:
            return jsonify({"error": "Missing required field: host_id_list"}), 400

        config = current_app.config["INVENTORY_CONFIG"]
        if len(tags) > config.api_bulk_tag_count_allowed:
            return jsonify(
                {"error": f"Too many tags provided. Maximum allowed is {config.api_bulk_tag_count_allowed}"}
            ), 400

        processed_hosts = 0
        not_found_hosts = []
        total_hosts = len(host_id_list)
        batch_size = config.api_bulk_tag_host_batch_size

        for i in range(0, total_hosts, batch_size):
            batch_ids = host_id_list[i : i + batch_size]
            with session_guard(db.session) as session:
                processed, missing = process_host_batch(session, identity, batch_ids, tags)
                processed_hosts += processed
                not_found_hosts.extend(missing)
                try:
                    session.flush()
                except IntegrityError as e:
                    current_app.logger.error(f"Database error in batch: {str(e)}")
                    session.rollback()
                    continue

        response = {"processed_hosts": processed_hosts, "total_hosts": total_hosts, "not_found_hosts": not_found_hosts}
        if not_found_hosts:
            response["warning"] = f"Some hosts were not found: {', '.join(not_found_hosts)}"
        return jsonify(response), 200

    except Exception as e:
        current_app.logger.error(f"Error in bulk_tag_hosts: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
