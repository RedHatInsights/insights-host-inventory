"""Real SQL commit/rollback and formatted audit evidence for customer mutations."""

import json
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from api import group as group_api
from app.auth.identity import Identity
from app.models import Group
from app.models import HostGroupAssoc
from app.models import InventoryView
from app.models import Staleness
from app.models import UserViewPreference
from app.models import db
from app.queue import host_mq
from app.serialization import serialize_canonical_facts
from lib import group_repository
from lib import views_repository
from tests.helpers.api_utils import _INPUT_DATA
from tests.helpers.api_utils import STALENESS_URL
from tests.helpers.api_utils import build_host_checkin_url
from tests.helpers.api_utils import build_views_url
from tests.helpers.api_utils import do_request
from tests.helpers.mq_utils import generate_kessel_workspace_message
from tests.helpers.staleness_test_constants import CUSTOM_STALENESS
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid

pytestmark = pytest.mark.usefixtures("restore_thread_context")

USER_ID = USER_IDENTITY["user"]["user_id"]
HEADERS = {"x-rh-insights-request-id": "domain-request"}
CONFIG = {"columns": [{"key": "display_name"}]}


def records(output):
    return [json.loads(line) for line in output.getvalue().splitlines()]


def assert_events(output, outcome):
    events = records(output)
    assert events
    for event in events:
        assert event["outcome"] == outcome
        assert event["principal"] == USER_ID
        assert event["principal_type"] == "User"
        assert event["org_id"] == USER_IDENTITY["org_id"]
        assert event["request_id"] == "domain-request"
        assert event["logger"] == "inventory.audit"
        assert event["timestamp"].endswith("+00:00")
    assert "private-" not in output.getvalue()
    assert USER_IDENTITY["user"]["email"] not in output.getvalue()
    return events


def fail_commit(monkeypatch, output):
    def commit(_session):
        assert not [event for event in records(output) if event["resource_type"] != "workspace_request"]
        raise RuntimeError("private-commit-error")

    monkeypatch.setattr(type(db.session()), "commit", commit)


@pytest.mark.usefixtures("event_producer_mock")
@pytest.mark.parametrize("fails", [False, True])
def test_checkin_result(fails, api_post, db_create_host, db_get_host, audit_output, monkeypatch):
    host = db_create_host()
    host_id, previous = str(host.id), host.last_check_in
    body = serialize_canonical_facts(host, include_none=False)
    if fails:
        fail_commit(monkeypatch, audit_output)
    status, _ = api_post(build_host_checkin_url(), body, extra_headers=HEADERS)
    assert status == (500 if fails else 201)
    (event,) = assert_events(audit_output, "failure" if fails else "success")
    assert (event["action"], event["resource_type"], event["resource_id"]) == ("CHECK_IN", "host", host_id)
    assert (db_get_host(host_id).last_check_in == previous) == fails


@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("operation", ["create", "update", "clone", "delete", "pin", "unpin"])
def test_view_result(
    operation,
    fails,
    api_post,
    api_patch,
    api_put,
    flask_client,
    db_create_view,
    db_create_user_view_preference,
    audit_output,
    monkeypatch,
):
    view = db_create_view(name="original", created_by=USER_ID)
    view_id = str(view.id)
    if operation == "unpin":
        db_create_user_view_preference(USER_IDENTITY["org_id"], USER_ID, view.id)
    count_before = InventoryView.query.count()
    if fails:
        fail_commit(monkeypatch, audit_output)
    if operation == "create":
        status, data = api_post(
            build_views_url(), {"name": "private-view", "configuration": CONFIG}, extra_headers=HEADERS
        )
    elif operation == "update":
        status, data = api_patch(build_views_url(view_id), {"name": "private-view"}, extra_headers=HEADERS)
    elif operation == "clone":
        status, data = api_post(build_views_url(view_id, clone=True), None, extra_headers=HEADERS)
    elif operation == "delete":
        status, data = do_request(flask_client.delete, build_views_url(view_id), USER_IDENTITY, extra_headers=HEADERS)
    elif operation == "pin":
        status, data = api_put(build_views_url(default=True), {"view_id": view_id}, extra_headers=HEADERS)
    else:
        status, data = do_request(
            flask_client.delete, build_views_url(default=True), USER_IDENTITY, extra_headers=HEADERS
        )
    expected = {"create": 201, "clone": 201, "delete": 204, "unpin": 204}.get(operation, 200)
    assert status == (500 if fails else expected)
    (event,) = assert_events(audit_output, "failure" if fails else "success")
    if operation in ("pin", "unpin"):
        assert event["resource_type"] == "view_preference"
        assert event["resource_id"] == f"{USER_IDENTITY['org_id']}:{USER_ID}"
        assert event["action"] == ("SET_DEFAULT" if operation == "pin" else "DELETE")
        assert bool(UserViewPreference.query.first()) == ((operation == "pin") != fails)
    else:
        assert event["resource_type"] == "saved_view"
        UUID(event["resource_id"])
        assert (
            event["action"]
            == {"create": "CREATE", "clone": "CREATE", "update": "UPDATE", "delete": "DELETE"}[operation]
        )
        if operation in ("create", "clone"):
            assert InventoryView.query.count() == count_before + (not fails)
            if not fails:
                assert event["resource_id"] == data["id"]
        elif operation == "delete":
            assert (db.session.get(InventoryView, UUID(view_id)) is not None) == fails
        else:
            assert db.session.get(InventoryView, UUID(view_id)).name == ("original" if fails else "private-view")


@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("operation", ["create", "update", "delete", "reset_post", "reset_patch"])
def test_staleness_result(
    operation, fails, api_post, api_patch, flask_client, db_create_staleness_culling, audit_output, monkeypatch
):
    if operation != "create":
        db_create_staleness_culling(**CUSTOM_STALENESS)
    if fails:
        fail_commit(monkeypatch, audit_output)
    if operation == "delete":
        status, _ = do_request(flask_client.delete, STALENESS_URL, USER_IDENTITY, extra_headers=HEADERS)
    else:
        send = api_post if operation in ("create", "reset_post") else api_patch
        body = (
            _INPUT_DATA
            if operation.startswith("reset")
            else {key: val + 1000 for key, val in CUSTOM_STALENESS.items()}
        )
        status, _ = send(STALENESS_URL, body, extra_headers=HEADERS)
    assert status == (500 if fails else {"create": 201, "reset_post": 201, "delete": 204}.get(operation, 200))
    (event,) = assert_events(audit_output, "failure" if fails else "success")
    assert (event["resource_type"], event["resource_id"]) == ("staleness_policy", USER_IDENTITY["org_id"])
    assert event["action"] == {"create": "CREATE", "update": "UPDATE"}.get(operation, "DELETE")
    row = Staleness.query.filter_by(org_id=USER_IDENTITY["org_id"]).one_or_none()
    if operation == "create":
        assert bool(row) == (not fails)
    elif operation != "update":
        assert bool(row) == fails
    else:
        assert row.conventional_time_to_stale == CUSTOM_STALENESS["conventional_time_to_stale"] + (
            0 if fails else 1000
        )


@pytest.mark.usefixtures("event_producer_mock")
@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("operation", ["create", "rename", "move", "delete", "remove"])
def test_group_result(
    operation,
    fails,
    api_create_group,
    api_patch_group,
    api_delete_groups,
    api_remove_hosts_from_group,
    db_create_group,
    db_create_host,
    db_create_host_group_assoc,
    audit_output,
    monkeypatch,
):
    source_id = str(db_create_group("source").id)
    target_id = str(db_create_group("target").id)
    ungrouped_id = str(db_create_group("Ungrouped Hosts", ungrouped=True).id)
    host_id = str(db_create_host().id)
    db_create_host_group_assoc(host_id, source_id)
    if fails:
        fail_commit(monkeypatch, audit_output)
    if operation == "create":
        status, data = api_create_group({"name": "private-new-group", "host_ids": [host_id]}, extra_headers=HEADERS)
    elif operation == "rename":
        status, data = api_patch_group(source_id, {"name": "private-renamed"}, extra_headers=HEADERS)
    elif operation == "move":
        status, data = api_patch_group(target_id, {"host_ids": [host_id]}, extra_headers=HEADERS)
    elif operation == "delete":
        status, data = api_delete_groups([source_id], extra_headers=HEADERS)
    else:
        status, data = api_remove_hosts_from_group(source_id, [host_id], extra_headers=HEADERS)
    assert status == (500 if fails else {"create": 201, "delete": 204, "remove": 204}.get(operation, 200))
    events = assert_events(audit_output, "failure" if fails else "success")
    actual_group = str(HostGroupAssoc.query.filter_by(host_id=host_id).one().group_id)
    memberships = {(e["action"], e["resource_id"]) for e in events if e["resource_type"] == "group_membership"}
    if fails:
        assert actual_group == source_id
        assert Group.query.filter_by(name="source").count() == 1
        assert Group.query.filter_by(name="private-new-group").count() == 0
        assert not memberships
    elif operation == "rename":
        assert actual_group == source_id
        assert not memberships
    else:
        expected_group = data["id"] if operation == "create" else target_id if operation == "move" else ungrouped_id
        assert actual_group == expected_group
        assert memberships == {("DELETE", f"{source_id}:{host_id}"), ("CREATE", f"{expected_group}:{host_id}")}


@pytest.mark.parametrize("fails", [False, True])
def test_view_delete_cascades(
    fails, flask_client, db_create_view, db_create_user_view_preference, audit_output, monkeypatch
):
    view = db_create_view(created_by=USER_ID, org_wide=True)
    view_id = str(view.id)
    for owner in (USER_ID, "another-user"):
        db_create_user_view_preference(USER_IDENTITY["org_id"], owner, view.id)
    if fails:
        fail_commit(monkeypatch, audit_output)
    status, _ = do_request(flask_client.delete, build_views_url(view_id), USER_IDENTITY, extra_headers=HEADERS)
    assert status == (500 if fails else 204)
    events = assert_events(audit_output, "failure" if fails else "success")
    assert len(events) == 3
    assert {e["resource_id"] for e in events if e["resource_type"] == "view_preference"} == {
        f"{USER_IDENTITY['org_id']}:{owner}" for owner in (USER_ID, "another-user")
    }
    assert UserViewPreference.query.count() == (2 if fails else 0)


def test_service_account_view(api_post, audit_output):
    status, data = api_post(
        build_views_url(),
        {"name": "private-view", "configuration": CONFIG},
        identity=SERVICE_ACCOUNT_IDENTITY,
        extra_headers=HEADERS,
    )
    assert status == 201
    (event,) = records(audit_output)
    assert event["principal"] == SERVICE_ACCOUNT_IDENTITY["service_account"]["client_id"]
    assert event["principal_type"] == "ServiceAccount"
    assert event["resource_id"] == data["id"]


@pytest.mark.usefixtures("event_producer_mock")
def test_workspace_acceptance_then_local_rollback(
    api_patch_group, inventory_config, db_create_group, audit_output, monkeypatch
):
    group_id = str(db_create_group("source").id)
    inventory_config.bypass_kessel = False
    monkeypatch.setattr(group_api, "patch_rbac_workspace", lambda *_args, **_kwargs: None)
    fail_commit(monkeypatch, audit_output)
    status, _ = api_patch_group(group_id, {"name": "private-new-name"}, extra_headers=HEADERS)
    assert status == 500
    accepted, rolled_back = records(audit_output)
    assert (accepted["action"], accepted["resource_type"], accepted["outcome"]) == (
        "REQUEST_UPDATE",
        "workspace_request",
        "success",
    )
    assert (rolled_back["action"], rolled_back["resource_type"], rolled_back["outcome"]) == (
        "UPDATE",
        "group",
        "failure",
    )
    assert accepted["resource_id"] == rolled_back["resource_id"] == group_id
    assert Group.query.filter_by(name="source").one()


def test_noops_are_not_mutations(
    api_patch,
    api_put,
    flask_client,
    db_create_view,
    db_create_user_view_preference,
    db_create_staleness_culling,
    audit_output,
):
    view = db_create_view(name="same", created_by=USER_ID)
    view_id = str(view.id)
    db_create_user_view_preference(USER_IDENTITY["org_id"], USER_ID, view.id)
    db_create_staleness_culling(**CUSTOM_STALENESS)
    assert api_patch(build_views_url(view_id), {"name": "same"})[0] == 200
    assert api_put(build_views_url(default=True), {"view_id": view_id})[0] == 200
    assert api_patch(STALENESS_URL, CUSTOM_STALENESS)[0] == 200
    assert records(audit_output) == []
    assert do_request(flask_client.delete, build_views_url(default=True), USER_IDENTITY)[0] == 204
    audit_output.seek(0)
    audit_output.truncate()
    assert do_request(flask_client.delete, build_views_url(default=True), USER_IDENTITY)[0] == 204
    assert records(audit_output) == []


@pytest.mark.usefixtures("event_producer_mock")
def test_group_publication_failure_keeps_committed_success(
    api_patch_group, db_create_group, audit_output, monkeypatch
):
    group_id = str(db_create_group("source").id)

    def publish(*_args, **_kwargs):
        raise RuntimeError("private-publication-error")

    monkeypatch.setattr(group_repository, "_process_host_changes", publish)
    status, _ = api_patch_group(group_id, {"name": "private-new-name"}, extra_headers=HEADERS)
    assert status == 500
    (event,) = assert_events(audit_output, "success")
    assert event["resource_id"] == group_id
    assert Group.query.filter_by(name="private-new-name").one()


def test_view_refresh_failure_keeps_committed_success(api_post, db_create_view, audit_output, monkeypatch):
    db_create_view(created_by=USER_ID)

    def refresh(*_args, **_kwargs):
        raise RuntimeError("private-refresh-error")

    monkeypatch.setattr(type(db.session()), "refresh", refresh)
    status, _ = api_post(
        build_views_url(), {"name": "private-new-view", "configuration": CONFIG}, extra_headers=HEADERS
    )
    assert status == 500
    (event,) = assert_events(audit_output, "success")
    assert db.session.get(InventoryView, UUID(event["resource_id"])).name == "private-new-view"


@pytest.mark.usefixtures("event_producer_mock")
def test_external_ungrouped_creation_is_not_attributed_to_api(
    api_delete_groups, db_create_group, audit_output, monkeypatch
):
    group_id = str(db_create_group("source").id)
    external_id = generate_uuid()

    def get_external(identity):
        with Session(db.engine) as other:
            other.add(Group(id=UUID(external_id), name="Ungrouped Hosts", org_id=identity.org_id, ungrouped=True))
            other.commit()
        return db.session.get(Group, UUID(external_id))

    monkeypatch.setattr(group_repository, "get_or_create_ungrouped_hosts_group_for_identity", get_external)
    status, _ = api_delete_groups([group_id], extra_headers=HEADERS)
    assert status == 204
    (event,) = assert_events(audit_output, "success")
    assert (event["action"], event["resource_id"]) == ("DELETE", group_id)
    assert db.session.get(Group, UUID(external_id)) is not None


@pytest.mark.usefixtures("event_producer_mock")
def test_concurrent_membership_move_is_not_attributed_to_rename(
    api_patch_group, db_create_group, db_create_host, db_create_host_group_assoc, audit_output, monkeypatch
):
    source_id = str(db_create_group("source").id)
    target_id = str(db_create_group("target").id)
    host_id = str(db_create_host().id)
    db_create_host_group_assoc(host_id, source_id)
    original = Group.patch

    def patch(group, data):
        with Session(db.engine) as other:
            other.query(HostGroupAssoc).filter_by(host_id=host_id).update({"group_id": UUID(target_id)})
            other.commit()
        return original(group, data)

    monkeypatch.setattr(Group, "patch", patch)
    status, _ = api_patch_group(source_id, {"name": "private-new-name"}, extra_headers=HEADERS)
    assert status == 200
    (event,) = assert_events(audit_output, "success")
    assert (event["action"], event["resource_type"], event["resource_id"]) == ("UPDATE", "group", source_id)
    assert str(HostGroupAssoc.query.filter_by(host_id=host_id).one().group_id) == target_id


def test_concurrent_group_delete_is_not_attributed_to_observer(db_create_group, audit_output):
    group_id = str(db_create_group("source").id)
    with group_repository._audited_group_transaction([group_id], Identity(USER_IDENTITY), "DELETE"):
        with Session(db.engine) as other:
            other.query(Group).filter_by(id=UUID(group_id)).delete()
            other.commit()
    assert records(audit_output) == []
    assert db.session.get(Group, UUID(group_id)) is None


def test_concurrent_group_update_is_not_attributed_to_observer(db_create_group, audit_output):
    group_id = str(db_create_group("source").id)
    with group_repository._audited_group_transaction([group_id], Identity(USER_IDENTITY), "UPDATE"):
        with Session(db.engine) as other:
            other.query(Group).filter_by(id=UUID(group_id)).update({"name": "external-name"})
            other.commit()
    assert records(audit_output) == []


@pytest.mark.usefixtures("flask_app")
def test_group_created_elsewhere_but_deleted_here_is_audited(audit_output):
    group_id = generate_uuid()
    identity = Identity(USER_IDENTITY)
    with group_repository._audited_group_transaction([group_id], identity, "DELETE"):
        with Session(db.engine) as other:
            other.add(Group(id=UUID(group_id), name="external", org_id=identity.org_id))
            other.commit()
        assert group_repository._delete_group(db.session.get(Group, UUID(group_id)), identity)
    events = records(audit_output)
    assert ("DELETE", group_id) in {(e["action"], e["resource_id"]) for e in events}
    assert db.session.get(Group, UUID(group_id)) is None


@pytest.mark.usefixtures("event_producer_mock")
def test_group_membership_noops_have_no_metadata_event(
    api_patch_group,
    api_remove_hosts_from_group,
    db_create_group,
    db_create_host,
    db_create_host_group_assoc,
    audit_output,
):
    group_id = str(db_create_group("source").id)
    db_create_group("Ungrouped Hosts", ungrouped=True)
    host_id = str(db_create_host().id)
    nonmember_id = str(db_create_host().id)
    db_create_host_group_assoc(host_id, group_id)
    assert api_patch_group(group_id, {"host_ids": [host_id]})[0] == 200
    assert api_remove_hosts_from_group(group_id, [nonmember_id])[0] == 404
    assert records(audit_output) == []


def test_concurrent_view_delete_is_not_attributed_to_observer(flask_client, db_create_view, audit_output, monkeypatch):
    view_id = str(db_create_view(created_by=USER_ID).id)
    original = views_repository._get_visible_view

    def load(*args):
        view = original(*args)
        with Session(db.engine) as other:
            other.query(InventoryView).filter_by(id=UUID(view_id)).delete()
            other.commit()
        return view

    monkeypatch.setattr(views_repository, "_get_visible_view", load)
    assert do_request(flask_client.delete, build_views_url(view_id), USER_IDENTITY)[0] == 404
    assert records(audit_output) == []


def test_preference_set_detects_concurrent_repin(
    api_put, db_create_view, db_create_user_view_preference, audit_output, monkeypatch
):
    desired = db_create_view(name="desired", created_by=USER_ID)
    other_view = db_create_view(name="other", created_by=USER_ID)
    desired_id, other_id = desired.id, other_view.id
    db_create_user_view_preference(USER_IDENTITY["org_id"], USER_ID, desired_id)
    original = type(db.session()).execute
    fired = False

    def execute(session, stmt, *args, **kwargs):
        nonlocal fired
        if getattr(stmt, "is_insert", False) and stmt.table.name == "user_view_preferences" and not fired:
            fired = True
            with Session(db.engine) as other:
                other.query(UserViewPreference).filter_by(user_id=USER_ID).update({"default_view_id": other_id})
                other.commit()
        return original(session, stmt, *args, **kwargs)

    monkeypatch.setattr(type(db.session()), "execute", execute)
    assert api_put(build_views_url(default=True), {"view_id": str(desired_id)}, extra_headers=HEADERS)[0] == 200
    (event,) = assert_events(audit_output, "success")
    assert event["action"] == "SET_DEFAULT"
    assert UserViewPreference.query.one().default_view_id == desired_id


def test_view_delete_does_not_claim_reassigned_preferences_and_blocks_new_pins(
    flask_client, db_create_view, db_create_user_view_preference, audit_output, monkeypatch
):
    removed_id = db_create_view(name="removed", created_by=USER_ID).id
    retained_id = db_create_view(name="retained", created_by=USER_ID).id
    db_create_user_view_preference(USER_IDENTITY["org_id"], USER_ID, removed_id)
    original = type(db.session()).execute
    fired = False

    def execute(session, stmt, *args, **kwargs):
        nonlocal fired
        if getattr(stmt, "is_delete", False) and stmt.table.name == "user_view_preferences" and not fired:
            fired = True
            with Session(db.engine) as other:
                other.query(UserViewPreference).filter_by(user_id=USER_ID).update({"default_view_id": retained_id})
                other.commit()
            with Session(db.engine) as other:
                other.execute(text("SET LOCAL lock_timeout = '100ms'"))
                other.add(
                    UserViewPreference(org_id=USER_IDENTITY["org_id"], user_id="new-user", default_view_id=removed_id)
                )
                with pytest.raises(OperationalError):
                    other.flush()  # The parent's row lock prevents a new FK reference.
                other.rollback()
        return original(session, stmt, *args, **kwargs)

    monkeypatch.setattr(type(db.session()), "execute", execute)
    assert (
        do_request(flask_client.delete, build_views_url(str(removed_id)), USER_IDENTITY, extra_headers=HEADERS)[0]
        == 204
    )
    (event,) = assert_events(audit_output, "success")
    assert event["resource_type"] == "saved_view"
    assert UserViewPreference.query.one().default_view_id == retained_id


def test_staleness_delete_locks_its_target(flask_client, db_create_staleness_culling, audit_output, monkeypatch):
    row_id = db_create_staleness_culling(**CUSTOM_STALENESS).id
    original = type(db.session()).delete
    attempted = False

    def delete(session, row, *args, **kwargs):
        nonlocal attempted
        if isinstance(row, Staleness):
            attempted = True
            with Session(db.engine) as other:
                other.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(OperationalError):
                    other.query(Staleness).filter_by(id=row_id).delete()
                other.rollback()
        return original(session, row, *args, **kwargs)

    monkeypatch.setattr(type(db.session()), "delete", delete)
    assert do_request(flask_client.delete, STALENESS_URL, USER_IDENTITY, extra_headers=HEADERS)[0] == 204
    assert attempted
    (event,) = assert_events(audit_output, "success")
    assert event["action"] == "DELETE"
    assert Staleness.query.count() == 0


@pytest.mark.parametrize(
    "message_spans,failure", [(True, None), (False, None), (True, "create_commit"), (True, "final_commit")]
)
def test_workspace_commits_preserve_actual_outcomes(
    message_spans,
    failure,
    flask_app,
    event_producer_mock,
    notification_event_producer_mock,
    audit_output,
    monkeypatch,
    otel_provider,
):
    provider, _ = otel_provider()
    monkeypatch.setattr(host_mq, "tracer", provider.get_tracer(__name__))
    monkeypatch.setattr(host_mq, "OTEL_MQ_ENABLED", True)
    monkeypatch.setattr(host_mq, "OTEL_MQ_MESSAGE_SPANS_ENABLED", message_spans)
    consumer = host_mq.WorkspaceMessageConsumer(
        MagicMock(), flask_app, event_producer_mock, notification_event_producer_mock
    )
    group_id = generate_uuid()
    messages = []
    for index, operation in enumerate(("create", "update"), 1):
        msg = MagicMock()
        msg.value.return_value = json.dumps(
            generate_kessel_workspace_message(operation, group_id, f"workspace-{index}")
        )
        msg.headers.return_value = [
            ("request_id", f"request-{index}".encode()),
            ("traceparent", f"00-{index:032x}-{index:016x}-01".encode()),
        ]
        msg.topic.return_value = "workspace-audit-test"
        messages.append(msg)
    original = type(db.session()).commit
    commits = 0

    def commit(session):
        nonlocal commits
        if not session.in_nested_transaction():
            commits += 1
            if (failure == "create_commit" and commits == 1) or (failure == "final_commit" and commits == 3):
                raise RuntimeError("private-workspace-commit-error")
        original(session)

    monkeypatch.setattr(type(db.session()), "commit", commit)
    monkeypatch.setattr(consumer, "post_process_rows", lambda: None)
    if failure:
        with pytest.raises(RuntimeError, match="private-workspace-commit-error"):
            consumer._run_batch(messages)
    else:
        consumer._run_batch(messages)
    events = records(audit_output)
    assert len(events) == (1 if failure == "create_commit" else 2)
    assert [event["outcome"] for event in events] == (
        ["failure"] if failure == "create_commit" else ["success", "success"]
    )
    for index, event in enumerate(events, 1):
        assert event["principal"] == "workspace-consumer"
        assert event["principal_type"] == "SystemActor"
        assert event["org_id"] == USER_IDENTITY["org_id"]
        assert event["request_id"] == f"request-{index}"
        assert event["trace_id"] == f"{index:032x}"
        assert bool(event["span_id"]) == message_spans
        assert event["resource_id"] == group_id
    assert (db.session.get(Group, UUID(group_id)) is None) == (failure == "create_commit")
