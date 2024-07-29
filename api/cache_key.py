import flask

from app import IDENTITY_HEADER
from app import process_identity_header


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
    if org_id is None or access_id is None:
        return
    key = f"{org_id}_{access_id}_{request.path}_{args}"
    return key


def make_system_cache_key(insights_id, org_id, owner_id):
    return f"insights_id={insights_id}_org={org_id}_user=SYSTEM-{owner_id}"
