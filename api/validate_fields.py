import flask

from app import system_profile_spec


def validate_fields_in_schema(fields):
    if fields.get("system_profile"):
        query_fields = list(fields.get("system_profile").keys())
        system_profile_schema = system_profile_spec()
        for field in query_fields:
            if field not in system_profile_schema.keys():
                flask.abort(400, f"Requested field '{field}' is not present in the system_profile schema.")
