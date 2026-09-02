import flask

from app import IDENTITY_HEADER
from app import process_identity_header
from app.auth import get_current_identity
from app.auth.forwarded_identity import get_satellite_forwarded_identity


def _encode_params(args):
    arg_key = ""
    for key, val in args.to_dict(flat=False).items():
        arg_key += f"{key}={val}"
    return arg_key


def make_key():
    request = flask.request
    args = str(hash(_encode_params(request.args)))
    encoded_id_header = request.headers.get(IDENTITY_HEADER)
    org_id, access_id = process_identity_header(encoded_id_header)
    forwarded_identity = get_satellite_forwarded_identity(get_current_identity())
    if forwarded_identity:
        access_id = f"{access_id}_{forwarded_identity}"
    key = f"{org_id}_{access_id}_{request.path}_{args}"
    return key


def make_system_cache_key(insights_id, org_id, owner_id, forwarded_identity=None):
    if not insights_id or not org_id or not owner_id:
        message = f"Invalid cache key encountered; insights_id={insights_id} org_id={org_id}, owner_id={owner_id}."
        raise Exception(message)  # TODO: Raise a more specific exception
    key = f"insights_id={insights_id}_org={org_id}_user=SYSTEM-{owner_id}"
    if forwarded_identity:
        key = f"{key}_subman={forwarded_identity}"
    return key
