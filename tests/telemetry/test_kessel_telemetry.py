"""Verify the standard gRPC interceptor against a local Kessel service."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from functools import partial
from types import SimpleNamespace

import grpc
import pytest
from kessel.inventory.v1beta2 import allowed_pb2
from kessel.inventory.v1beta2 import check_bulk_request_pb2
from kessel.inventory.v1beta2 import check_bulk_response_pb2
from kessel.inventory.v1beta2 import check_for_update_request_pb2
from kessel.inventory.v1beta2 import check_for_update_response_pb2
from kessel.inventory.v1beta2 import check_request_pb2
from kessel.inventory.v1beta2 import check_response_pb2
from kessel.inventory.v1beta2 import inventory_service_pb2_grpc
from kessel.inventory.v1beta2 import resource_reference_pb2
from kessel.inventory.v1beta2 import streamed_list_objects_request_pb2
from kessel.inventory.v1beta2 import streamed_list_objects_response_pb2
from kessel.inventory.v1beta2 import subject_reference_pb2
from opentelemetry import trace
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.propagate import extract
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF

from app import telemetry
from app.auth.identity import Identity
from app.auth.rbac import KesselResourceTypes
from lib.kessel import Kessel
from tests.helpers.test_utils import USER_IDENTITY

SERVICE = "kessel.inventory.v1beta2.KesselInventoryService"
PRIVATE_ERROR = "private-host-1 redhat/private-user bearer-token-secret"


class FakeKessel:
    def __init__(self):
        self.calls = []
        self.errors = {}
        self.stream_error = None
        self.stream_observer = None
        bulk = check_bulk_response_pb2.CheckBulkResponse()
        for resource_id in ("private-host-1", "private-host-2"):
            pair = bulk.pairs.add()
            pair.request.object.resource_id = resource_id
            pair.item.allowed = allowed_pb2.ALLOWED_TRUE
        self.responses = {
            "Check": check_response_pb2.CheckResponse(allowed=allowed_pb2.ALLOWED_TRUE),
            "CheckForUpdate": check_for_update_response_pb2.CheckForUpdateResponse(allowed=allowed_pb2.ALLOWED_TRUE),
            "CheckBulk": bulk,
        }
        workspace = streamed_list_objects_response_pb2.StreamedListObjectsResponse()
        workspace.object.resource_id = "private-workspace-1"
        self.pages = {"": [workspace]}

    def _observe(self, method, request, context):
        self.calls.append((method, request, dict(context.invocation_metadata())))
        if method in self.errors:
            context.abort(self.errors[method], PRIVATE_ERROR)

    def unary(self, method, request, context):
        self._observe(method, request, context)
        return self.responses[method]

    def stream(self, request, context):
        self._observe("StreamedListObjects", request, context)
        for response in self.pages[request.pagination.continuation_token]:
            if self.stream_observer:
                self.stream_observer()
            yield response
        if self.stream_error:
            context.abort(self.stream_error, PRIVATE_ERROR)


@pytest.fixture
def kessel_service():
    service = FakeKessel()
    pool = ThreadPoolExecutor(max_workers=2)
    server = grpc.server(pool)
    requests = {
        "Check": check_request_pb2.CheckRequest,
        "CheckBulk": check_bulk_request_pb2.CheckBulkRequest,
        "CheckForUpdate": check_for_update_request_pb2.CheckForUpdateRequest,
    }
    handlers = {
        method: grpc.unary_unary_rpc_method_handler(
            partial(service.unary, method),
            request_deserializer=request_type.FromString,
            response_serializer=type(service.responses[method]).SerializeToString,
        )
        for method, request_type in requests.items()
    }
    handlers["StreamedListObjects"] = grpc.unary_stream_rpc_method_handler(
        service.stream,
        request_deserializer=streamed_list_objects_request_pb2.StreamedListObjectsRequest.FromString,
        response_serializer=streamed_list_objects_response_pb2.StreamedListObjectsResponse.SerializeToString,
    )
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(SERVICE, handlers),))
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    yield service, f"127.0.0.1:{port}"
    server.stop(0).wait()
    pool.shutdown()


@pytest.fixture
def kessel_spans(monkeypatch, otel_provider):
    provider, exporter = otel_provider(set_global=True)
    monkeypatch.setattr(telemetry, "OTEL_ENABLED", True)
    monkeypatch.setattr(telemetry, "OTEL_HTTP_OUTBOUND_ENABLED", True)
    return provider.get_tracer("HBI request"), exporter


@pytest.fixture
def make_client(kessel_service, kessel_spans, monkeypatch):  # noqa: ARG001
    _, target = kessel_service
    clients = []
    subject = subject_reference_pb2.SubjectReference(
        resource=resource_reference_pb2.ResourceReference(resource_type="principal", resource_id="redhat/private-user")
    )
    monkeypatch.setattr("lib.kessel.principal_from_rh_identity", lambda _identity: subject)
    monkeypatch.setattr("lib.kessel.get_flag_value", lambda *_args: False)

    def factory(*, master=True, outbound=True):
        monkeypatch.setattr(telemetry, "OTEL_ENABLED", master)
        monkeypatch.setattr(telemetry, "OTEL_HTTP_OUTBOUND_ENABLED", outbound)
        client = Kessel(
            SimpleNamespace(
                kessel_inventory_api_endpoint=target,
                kessel_auth_enabled=False,
                kessel_insecure=True,
                kessel_timeout=2.0,
            )
        )
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.close()


def call_kessel(client, method):
    identity = Identity(USER_IDENTITY)
    if method == "CheckForUpdate":
        return client.check_for_update(identity, KesselResourceTypes.HOST.update, ["private-host-1"])
    if method == "StreamedListObjects":
        return client.ListAllowedWorkspaces(identity, "inventory_host_view")
    ids = ["private-host-1", "private-host-2"] if method == "CheckBulk" else ["private-host-1"]
    return client.check(identity, KesselResourceTypes.HOST.view, ids)


def assert_safe_span(span):
    assert not span.events
    for private_value in ("private-", "secret"):
        assert private_value not in span.to_json()


@pytest.mark.parametrize(
    "method,relation,resource_type,resource_count",
    [
        ("Check", "view", "host", 1),
        ("CheckBulk", "view", "host", 2),
        ("CheckForUpdate", "update", "host", 1),
        ("StreamedListObjects", "inventory_host_view", "workspace", 1),
    ],
)
def test_standard_grpc_spans_and_propagation(
    make_client, kessel_service, kessel_spans, method, relation, resource_type, resource_count
):
    service, target = kessel_service
    tracer, exporter = kessel_spans
    observations = []
    service.stream_observer = lambda: observations.append(exporter.get_finished_spans())
    client = make_client()
    with tracer.start_as_current_span("HBI request") as parent:
        result = call_kessel(client, method)
    assert result == (["private-workspace-1"] if method == "StreamedListObjects" else (True, []))

    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    span = spans[0]
    assert span.instrumentation_scope.name == "opentelemetry.instrumentation.grpc"
    assert span.kind == trace.SpanKind.CLIENT
    assert span.parent.span_id == parent.get_span_context().span_id
    assert span.context.trace_id == parent.get_span_context().trace_id
    assert span.name == f"/{SERVICE}/{method}"
    assert span.end_time > span.start_time
    assert span.status.status_code == trace.StatusCode.UNSET
    expected = {
        "rpc.system": "grpc",
        "rpc.service": SERVICE,
        "rpc.method": method,
        "rpc.grpc.status_code": 0,
        "server.address": "127.0.0.1",
        "server.port": int(target.rsplit(":", 1)[1]),
        "kessel.grpc.status_name": "OK",
        "kessel.response.complete": True,
        "kessel.relation": relation,
        "kessel.resource_type": resource_type,
        "kessel.resource_count": resource_count,
    }
    assert {key: span.attributes[key] for key in expected} == expected
    if method == "StreamedListObjects":
        assert span.attributes["kessel.operation"] == "ListAllowedWorkspaces"
        assert observations == [()]  # The span stays open while the stream is consumed.
    else:
        assert span.attributes["kessel.allowed"] is True
    assert_safe_span(span)
    assert len(service.calls) == 1
    _, request, metadata = service.calls[0]
    subject = request.items[0].subject if method == "CheckBulk" else request.subject
    assert "private-user" in str(subject)
    downstream = trace.get_current_span(extract(metadata)).get_span_context()
    assert downstream.trace_id == span.context.trace_id
    assert downstream.span_id == span.context.span_id


@pytest.mark.parametrize(
    "method,allowed,decision",
    [
        ("Check", allowed_pb2.ALLOWED_FALSE, "ALLOWED_FALSE"),
        ("CheckForUpdate", allowed_pb2.ALLOWED_UNSPECIFIED, "ALLOWED_UNSPECIFIED"),
        ("Check", 77, "ALLOWED_UNRECOGNIZED"),
    ],
)
def test_check_response_outcomes(make_client, kessel_service, kessel_spans, method, allowed, decision):
    service, _ = kessel_service
    _, exporter = kessel_spans
    service.responses[method].allowed = allowed

    assert call_kessel(make_client(), method) == (False, ["private-host-1"])

    span = exporter.get_finished_spans()[0]
    assert span.attributes["rpc.grpc.status_code"] == 0
    assert span.attributes["kessel.allowed"] is False
    assert span.attributes["kessel.response.allowed"] == decision
    assert span.attributes["kessel.response.complete"] is True
    if allowed == allowed_pb2.ALLOWED_FALSE:
        assert span.status.status_code == trace.StatusCode.UNSET
        assert "error.type" not in span.attributes
    else:
        assert span.status.status_code == trace.StatusCode.ERROR
        assert span.attributes["error.type"] == span.status.description == "KesselIndeterminateDecision"
    assert_safe_span(span)


@pytest.mark.parametrize(
    "outcome,counts,error_type",
    [
        ("denied", (1, 1, 0, 0), None),
        ("indeterminate", (1, 0, 1, 0), "KesselIndeterminateDecision"),
        ("item_errors", (0, 0, 0, 2), "KesselBulkItemError"),
        ("incomplete", (1, 0, 0, 0), "KesselIncompleteResponse"),
    ],
)
def test_bulk_response_outcomes(make_client, kessel_service, kessel_spans, outcome, counts, error_type):
    service, _ = kessel_service
    _, exporter = kessel_spans
    response = service.responses["CheckBulk"]
    if outcome == "incomplete":
        del response.pairs[1]
    elif outcome == "item_errors":
        for pair, code in zip(response.pairs, (13, 14), strict=True):
            pair.error.code = code
            pair.error.message = PRIVATE_ERROR
            pair.error.details.add(type_url=PRIVATE_ERROR, value=PRIVATE_ERROR.encode())
    else:
        response.pairs[1].item.allowed = (
            allowed_pb2.ALLOWED_FALSE if outcome == "denied" else allowed_pb2.ALLOWED_UNSPECIFIED
        )

    rejected = ["private-host-1", "private-host-2"] if outcome in ("incomplete", "item_errors") else ["private-host-2"]
    assert call_kessel(make_client(), "CheckBulk") == (False, rejected)

    span = exporter.get_finished_spans()[0]
    assert span.attributes["rpc.grpc.status_code"] == 0
    assert span.attributes["kessel.grpc.status_name"] == "OK"
    assert span.attributes["kessel.allowed"] is False
    assert span.attributes["kessel.denied_count"] == len(rejected)
    assert span.attributes["kessel.response.complete"] is (outcome != "incomplete")
    assert span.attributes["kessel.response.count"] == (1 if outcome == "incomplete" else 2)
    for name, count in zip(("allowed", "denied", "indeterminate", "error"), counts, strict=True):
        assert span.attributes[f"kessel.response.{name}_count"] == count
    if error_type:
        assert span.status.status_code == trace.StatusCode.ERROR
        assert span.attributes["error.type"] == span.status.description == error_type
    else:
        assert span.status.status_code == trace.StatusCode.UNSET
        assert "error.type" not in span.attributes
    if outcome == "item_errors":
        assert span.attributes["kessel.response.error_codes"] == (13, 14)
        assert span.attributes["kessel.response.error_status_names"] == ("INTERNAL", "UNAVAILABLE")
    assert_safe_span(span)


@pytest.mark.parametrize(
    "method,code",
    [
        ("Check", grpc.StatusCode.PERMISSION_DENIED),
        ("CheckBulk", grpc.StatusCode.UNAVAILABLE),
        ("CheckForUpdate", grpc.StatusCode.INTERNAL),
        ("StreamedListObjects", grpc.StatusCode.DEADLINE_EXCEEDED),
    ],
)
def test_grpc_error_diagnostics(make_client, kessel_service, kessel_spans, method, code):
    service, _ = kessel_service
    tracer, exporter = kessel_spans
    observations = []
    if method == "StreamedListObjects":
        service.stream_error = code
        service.stream_observer = lambda: observations.append(exporter.get_finished_spans())
    else:
        service.errors[method] = code
    client = make_client()
    with tracer.start_as_current_span("HBI request") as parent:
        result = call_kessel(client, method)

    assert result == [] if method == "StreamedListObjects" else result[0] is False
    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    span = spans[0]
    assert span.parent.span_id == parent.get_span_context().span_id
    assert span.attributes["rpc.grpc.status_code"] == code.value[0]
    assert span.attributes["kessel.grpc.status_name"] == code.name
    assert span.attributes["kessel.response.complete"] is False
    assert span.status.status_code == trace.StatusCode.ERROR
    assert span.attributes["error.type"] == span.status.description == code.name
    if code == grpc.StatusCode.PERMISSION_DENIED:
        assert span.attributes["kessel.allowed"] is False
    if method == "StreamedListObjects":
        assert span.attributes["kessel.response.count"] == span.attributes["kessel.resource_count"] == 1
        assert observations == [()]
    assert_safe_span(span)


@pytest.mark.parametrize(
    "master,outbound,suppressed",
    [
        pytest.param(False, True, False, id="master-disabled"),
        pytest.param(True, False, False, id="outbound-disabled"),
        pytest.param(True, True, True, id="suppressed"),
    ],
)
def test_tracing_disabled_or_suppressed(make_client, kessel_service, kessel_spans, master, outbound, suppressed):
    service, _ = kessel_service
    tracer, exporter = kessel_spans
    client = make_client(master=master, outbound=outbound)
    with tracer.start_as_current_span("HBI request") as parent:
        with suppress_instrumentation() if suppressed else nullcontext():
            assert call_kessel(client, "StreamedListObjects") == ["private-workspace-1"]

    assert [span.name for span in exporter.get_finished_spans()] == ["HBI request"]
    assert not parent.attributes
    assert "traceparent" not in service.calls[0][2]


@pytest.mark.parametrize("method", ["Check", "StreamedListObjects"])
def test_unsampled_calls_preserve_grpc_errors(make_client, kessel_service, otel_provider, method):
    service, _ = kessel_service
    _, exporter = otel_provider(set_global=True, sampler=ALWAYS_OFF)
    service.errors[method] = grpc.StatusCode.INTERNAL
    client = make_client()
    request = (
        check_request_pb2.CheckRequest(relation="view")
        if method == "Check"
        else streamed_list_objects_request_pb2.StreamedListObjectsRequest(relation="inventory_host_view")
    )

    with pytest.raises(grpc.RpcError) as error:
        result = getattr(client.inventory_svc, method)(request, timeout=2)
        if method == "StreamedListObjects":
            list(result)

    assert error.value.code() == grpc.StatusCode.INTERNAL
    assert error.value.details() == PRIVATE_ERROR
    assert not exporter.get_finished_spans()


@pytest.mark.parametrize("workspace_count", [0, 2], ids=["empty", "pagination"])
def test_workspace_results(make_client, kessel_service, kessel_spans, workspace_count):
    service, _ = kessel_service
    tracer, exporter = kessel_spans
    service.pages = {"": []}
    for index in range(workspace_count):
        response = streamed_list_objects_response_pb2.StreamedListObjectsResponse()
        response.object.resource_id = f"private-workspace-{index + 1}"
        if index + 1 < workspace_count:
            response.pagination.continuation_token = f"private-page-{index + 1}"
        service.pages[f"private-page-{index}" if index else ""] = [response]
    client = make_client()
    with tracer.start_as_current_span("HBI request") as parent:
        assert call_kessel(client, "StreamedListObjects") == [
            f"private-workspace-{index + 1}" for index in range(workspace_count)
        ]

    spans = exporter.get_finished_spans()[:-1]
    assert len(spans) == len(service.calls) == max(1, workspace_count)
    for span in spans:
        assert span.parent.span_id == parent.get_span_context().span_id
        assert (
            span.attributes["kessel.resource_count"]
            == span.attributes["kessel.response.count"]
            == min(1, workspace_count)
        )
        assert span.attributes["kessel.response.complete"] is True
        assert span.attributes["rpc.grpc.status_code"] == 0
        assert_safe_span(span)


@pytest.mark.parametrize(
    "target",
    ["dns:///kessel.test:9000", "https://user:secret@kessel.test:9000/private-host-1?token=secret"],
)
def test_channel_preserves_metadata_and_sanitizes_target(kessel_service, kessel_spans, target):
    service, address = kessel_service
    _, exporter = kessel_spans
    with grpc.insecure_channel(address) as channel:
        wrapped = telemetry.instrument_kessel_grpc_channel(channel, target)
        client = inventory_service_pb2_grpc.KesselInventoryServiceStub(wrapped)
        client.Check(
            check_request_pb2.CheckRequest(
                relation="view", object=resource_reference_pb2.ResourceReference(resource_type="host")
            ),
            metadata=(("authorization", "bearer-token-secret"), ("x-request-id", "request-1")),
            timeout=2,
        )

    metadata = service.calls[0][2]
    assert metadata["authorization"] == "bearer-token-secret"
    assert metadata["x-request-id"] == "request-1"
    assert "traceparent" in metadata
    span = exporter.get_finished_spans()[0]
    assert span.attributes["server.address"] == "kessel.test"
    assert span.attributes["server.port"] == 9000
    assert_safe_span(span)
