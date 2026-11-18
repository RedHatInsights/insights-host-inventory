"""Audit output must preserve attributable fields without exposing diagnostic payloads."""

import json
import logging
import subprocess
import sys
from copy import deepcopy
from datetime import datetime
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest
from flask import Flask

from app import audit
from app.auth.identity import Identity
from app.auth.identity import create_mock_identity_with_org_id
from app.logging import threadctx
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import X509_IDENTITY


@pytest.fixture(autouse=True)
def restore_thread_context():
    previous = threadctx.__dict__.copy()
    yield
    threadctx.__dict__.clear()
    threadctx.__dict__.update(previous)


@pytest.fixture
def audit_output(monkeypatch):
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(audit.AuditFormatter())
    logger = logging.Logger("inventory.audit", level=logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    monkeypatch.setattr(audit, "logger", logger)
    yield stream
    handler.close()


@pytest.mark.parametrize(
    "identity_data, principal, principal_type",
    [
        (USER_IDENTITY, USER_IDENTITY["user"]["user_id"], "User"),
        (SERVICE_ACCOUNT_IDENTITY, SERVICE_ACCOUNT_IDENTITY["service_account"]["client_id"], "ServiceAccount"),
        (SYSTEM_IDENTITY, SYSTEM_IDENTITY["system"]["cn"], "System"),
        ({**X509_IDENTITY, "org_id": "test"}, X509_IDENTITY["x509"]["subject_dn"], "X509"),
        (
            {**SERVICE_ACCOUNT_IDENTITY, "type": "Associate"},
            SERVICE_ACCOUNT_IDENTITY["service_account"]["client_id"],
            "Associate",
        ),
    ],
)
def test_context_extracts_only_actor_identifiers(identity_data, principal, principal_type):
    context = audit.capture_audit_context(Identity(deepcopy(identity_data)))

    assert context.principal == principal
    assert context.principal_type == principal_type
    assert context.org_id == identity_data["org_id"]


def test_user_without_id_uses_validated_username():
    identity_data = deepcopy(USER_IDENTITY)
    del identity_data["user"]["user_id"]

    context = audit.capture_audit_context(Identity(identity_data))

    assert context.principal == USER_IDENTITY["user"]["username"]
    assert context.principal_type == "User"


def test_synthetic_identity_does_not_invent_a_user():
    context = audit.capture_audit_context(create_mock_identity_with_org_id("org-a"))

    assert context.org_id == "org-a"
    assert context.principal is None
    assert context.principal_type is None


def test_shared_secret_does_not_identify_a_caller_or_tenant(monkeypatch):
    monkeypatch.setenv("INVENTORY_SHARED_SECRET", "credential-must-not-be-logged")
    identity = Identity(token="credential-must-not-be-logged")

    context = audit.capture_audit_context(identity)

    assert context.principal is None
    assert context.principal_type == "TrustedSystem"
    assert context.org_id is None
    assert audit.capture_audit_context(identity, org_id="org-a").org_id == "org-a"


def test_context_rejects_ambiguous_actor_or_mismatched_tenant():
    identity = Identity(deepcopy(USER_IDENTITY))

    with pytest.raises(ValueError, match="either an identity or a system actor"):
        audit.capture_audit_context(identity, system_actor="host-reaper")
    with pytest.raises(ValueError, match="must match the validated identity"):
        audit.capture_audit_context(identity, org_id="another-org")


def test_request_context_does_not_trust_forwarded_ip_headers():
    app = Flask(__name__)
    with app.test_request_context(
        headers={
            "x-rh-insights-request-id": "request-a",
            "X-Forwarded-For": "192.0.2.10",
            "True-Client-IP": "192.0.2.11",
            "x-rh-identity": "unvalidated-header-must-not-be-used",
        },
    ):
        context = audit.capture_audit_context()
        explicit = audit.capture_audit_context(request_id="message-a", user_ip="2001:0db8::1")

    assert context.request_id == "request-a"
    assert context.principal is None
    assert context.user_ip is None
    assert explicit.request_id == "message-a"
    assert explicit.user_ip == "2001:db8::1"


def test_context_without_request_does_not_reuse_thread_local_attribution():
    threadctx.request_id = "previous-request"
    threadctx.org_id = "previous-org"
    threadctx.account_number = "previous-account"

    context = audit.capture_audit_context()

    assert context.request_id is None
    assert context.org_id is None
    assert context.principal is None


def test_formatted_output_preserves_contract_and_json_record_boundary(audit_output):
    context = audit.capture_audit_context(
        Identity(deepcopy(USER_IDENTITY)), request_id="request-a", user_ip="192.0.2.10"
    )
    audit.log_audit_event(
        action="UPDATE", resource_type="host", resource_id="host-a\nsecond-line", outcome="success", context=context
    )

    lines = audit_output.getvalue().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["action"] == "UPDATE"
    assert event["resource_type"] == "host"
    assert event["resource_id"] == "host-a\nsecond-line"
    assert event["outcome"] == "success"
    assert event["principal"] == USER_IDENTITY["user"]["user_id"]
    assert event["org_id"] == USER_IDENTITY["org_id"]
    assert event["request_id"] == "request-a"
    assert event["user_ip"] == "192.0.2.10"
    assert event["logger"] == "inventory.audit"
    assert event["level"] == "INFO"
    assert datetime.fromisoformat(event["timestamp"]).utcoffset().total_seconds() == 0
    assert USER_IDENTITY["user"]["email"] not in lines[0]


def test_failure_and_system_actor_support_uuid_or_unknown_resource(audit_output):
    resource_id = UUID("e3f9b2dd-1c8b-4d89-8b89-2ff9d8dc7cc4")
    context = audit.capture_audit_context(system_actor="host-reaper", org_id="org-a", request_id="message-a")
    audit.log_audit_event(
        action="DELETE", resource_type="host", resource_id=resource_id, outcome="success", context=context
    )
    audit.log_audit_event(
        action="AUTHORIZE", resource_type="host", outcome="failure", context=context, reason="permission_denied"
    )

    success, failure = map(json.loads, audit_output.getvalue().splitlines())
    assert success["resource_id"] == str(resource_id)
    assert success["principal"] == "host-reaper"
    assert success["principal_type"] == "SystemActor"
    assert success["org_id"] == "org-a"
    assert failure["resource_id"] is None
    assert failure["outcome"] == "failure"
    assert failure["reason"] == "permission_denied"


def test_deferred_context_preserves_actor_tenant_request_and_original_trace(audit_output, otel_provider):
    provider, _ = otel_provider()
    tracer = provider.get_tracer("audit-test")
    original_identity = Identity(deepcopy(USER_IDENTITY))
    with tracer.start_as_current_span("original") as original_span:
        original = audit.capture_audit_context(original_identity, request_id="request-a")

    other_identity = deepcopy(USER_IDENTITY)
    other_identity["org_id"] = "org-b"
    other_identity["user"]["user_id"] = "user-b"
    with tracer.start_as_current_span("another-message") as another_span:
        another = audit.capture_audit_context(Identity(other_identity), request_id="request-b")
        original_identity.user["user_id"] = "changed-after-capture"
        threadctx.request_id = "request-b"
        for context in (original, another):
            audit.log_audit_event(
                action="UPDATE", resource_type="host", resource_id="host-a", outcome="success", context=context
            )

    first, second = map(json.loads, audit_output.getvalue().splitlines())
    assert (first["org_id"], first["principal"], first["request_id"]) == (
        USER_IDENTITY["org_id"],
        USER_IDENTITY["user"]["user_id"],
        "request-a",
    )
    assert first["trace_id"] == f"{original_span.get_span_context().trace_id:032x}"
    assert first["span_id"] == f"{original_span.get_span_context().span_id:016x}"
    assert (second["org_id"], second["principal"], second["request_id"]) == ("org-b", "user-b", "request-b")
    assert second["trace_id"] == f"{another_span.get_span_context().trace_id:032x}"


def test_formatter_excludes_arbitrary_extras_messages_and_exception_text():
    try:
        raise ValueError("credential-secret")
    except ValueError:
        record = logging.makeLogRecord(
            {
                "name": "inventory.audit",
                "levelname": "INFO",
                "msg": "raw-identity-secret",
                "action": "AUTHENTICATE",
                "resource_type": "host",
                "outcome": "failure",
                "token": "bearer-secret",
                "body": {"password": "payload-secret"},
                "exc_info": sys.exc_info(),
            }
        )
    formatted = audit.AuditFormatter().format(record)

    assert "secret" not in formatted
    assert "password" not in formatted
    assert json.loads(formatted)["outcome"] == "failure"


def test_default_configuration_emits_once_at_info_without_parent_context_overwrite():
    # Use a subprocess because dictConfig closes/replaces global pytest log handlers.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import io
import logging
import os
from app import audit
from app import logging as app_logging

os.environ.pop('INVENTORY_LOGGING_CONFIG_FILE', None)
os.environ['INVENTORY_LOG_LEVEL'] = 'CRITICAL'
app_logging.cloudwatch_handler = logging.NullHandler
app_logging.configure_logging()
root_output = io.StringIO()
logging.getLogger().addHandler(logging.StreamHandler(root_output))
app_logging.threadctx.org_id = 'wrong-org'
app_logging.threadctx.request_id = 'wrong-request'
context = audit.capture_audit_context(system_actor='host-reaper', org_id='org-a', request_id='message-a')
audit.log_audit_event(action='DELETE', resource_type='host', resource_id='host-a', outcome='success', context=context)
assert root_output.getvalue() == ''
logging.getLogger('inventory').critical('diagnostic-format-preserved')
""",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    lines = result.stdout.splitlines()
    assert len(lines) == 2
    event = json.loads(lines[0])
    assert event["org_id"] == "org-a"
    assert event["request_id"] == "message-a"
    assert event["level"] == "INFO"
    assert lines[1].startswith("[")
    assert lines[1].endswith("diagnostic-format-preserved")
