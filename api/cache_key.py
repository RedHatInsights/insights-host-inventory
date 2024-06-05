import flask

from app import IDENTITY_HEADER
from app import process_identity_header


def make_key():
    request = flask.request
    args = str(hash(frozenset(request.args.items())))
    encoded_id_header = request.headers.get(IDENTITY_HEADER)
    org_id, access_id = process_identity_header(encoded_id_header)
    if org_id is None or access_id is None:
        return
    key = f"{org_id}_{access_id}_{request.path}_{args}"
    return key
