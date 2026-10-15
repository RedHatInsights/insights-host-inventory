"""Safe Kessel context for the standard OpenTelemetry gRPC client interceptor.

The library owns span lifetimes, RPC status, and trace context propagation. This
module adds authorization context and prevents server error text from being
recorded. Its streaming interceptor fills the library's streaming hook gap.
"""

from contextlib import contextmanager
from urllib.parse import urlparse

import grpc
from kessel.inventory.v1beta2 import allowed_pb2
from opentelemetry import trace
from opentelemetry.instrumentation.grpc import client_interceptor
from opentelemetry.instrumentation.grpc import grpcext
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from wrapt import ObjectProxy

_GRPC_STATUS_NAMES = {code.value[0]: code.name for code in grpc.StatusCode}


class _SafeSpan(ObjectProxy):
    def set_status(self, status, description=None):  # noqa: ARG002
        if not self.is_recording():
            return
        # Upstream includes raw exceptions. Use only our controlled error labels.
        code = status.status_code if isinstance(status, trace.Status) else status
        safe_description = self.__wrapped__.attributes.get("error.type") if code == trace.StatusCode.ERROR else None
        self.__wrapped__.set_status(code, safe_description)

    def record_exception(self, exception, *args, **kwargs):
        # Retain an exception's class, excluding messages and stack traces.
        if not isinstance(exception, grpc.RpcError):
            self.__wrapped__.set_attribute("error.type", type(exception).__name__)
            self.set_status(trace.StatusCode.ERROR)

    def set_attribute(self, key, value):
        self.__wrapped__.set_attribute(key, value)
        if key == "rpc.grpc.status_code":
            name = _GRPC_STATUS_NAMES.get(value, "UNRECOGNIZED")
            self.__wrapped__.set_attribute("kessel.grpc.status_name", name)
            if value != grpc.StatusCode.OK.value[0]:
                self.__wrapped__.set_attribute("error.type", name)
                self.set_status(trace.StatusCode.ERROR)
            if value == grpc.StatusCode.PERMISSION_DENIED.value[0]:
                self.__wrapped__.set_attribute("kessel.allowed", False)


class _SafeTracer(ObjectProxy):
    def __init__(self, tracer, peer_attributes):
        super().__init__(tracer)
        self._self_peer_attributes = peer_attributes

    @contextmanager
    def start_as_current_span(self, *args, **kwargs):
        kwargs["attributes"] = {
            **kwargs.get("attributes", {}),
            **self._self_peer_attributes,
            "kessel.grpc.status_name": "OK",
            "kessel.response.complete": False,
        }
        kwargs["record_exception"] = False
        kwargs["set_status_on_exception"] = False
        with self.__wrapped__.start_as_current_span(*args, **kwargs) as span:
            safe_span = _SafeSpan(span)
            try:
                yield safe_span
            except Exception as error:
                # The library handles gRPC errors; cover unexpected stream errors too.
                if span.is_recording():
                    safe_span.set_status(trace.StatusCode.ERROR)
                    safe_span.record_exception(error)
                raise


class _SafeTracerProvider(ObjectProxy):
    def __init__(self, provider, target: str):
        super().__init__(provider)
        parsed = urlparse(target if "://" in target else f"//{target}")
        if not parsed.netloc:
            parsed = urlparse(f"//{parsed.path.lstrip('/')}")
        self._self_peer_attributes: dict[str, str | int] = {"server.address": parsed.hostname or "unknown"}
        if parsed.port is not None:
            self._self_peer_attributes["server.port"] = parsed.port

    def get_tracer(self, *args, **kwargs):
        return _SafeTracer(self.__wrapped__.get_tracer(*args, **kwargs), self._self_peer_attributes)


def _request_hook(span, request):
    if not span.is_recording():
        return

    if hasattr(request, "items"):
        span.set_attribute("kessel.resource_count", len(request.items))
        if not request.items:
            return
        request = request.items[0]
    elif hasattr(request, "object"):
        span.set_attribute("kessel.resource_count", 1)

    span.set_attribute("kessel.relation", request.relation)
    if hasattr(request, "object_type"):
        span.set_attribute("kessel.resource_type", request.object_type.resource_type)
        span.set_attribute("kessel.operation", "ListAllowedWorkspaces")
    else:
        span.set_attribute("kessel.resource_type", request.object.resource_type)


def _response_hook(span, response):
    if not span.is_recording():
        return

    if hasattr(response, "pairs"):
        count = span.attributes["kessel.resource_count"]
        allowed_count = sum(
            pair.HasField("item") and pair.item.allowed == allowed_pb2.ALLOWED_TRUE for pair in response.pairs
        )
        denied_count = sum(
            pair.HasField("item") and pair.item.allowed == allowed_pb2.ALLOWED_FALSE for pair in response.pairs
        )
        errors = [pair.error.code for pair in response.pairs if pair.HasField("error")]
        indeterminate_count = len(response.pairs) - allowed_count - denied_count - len(errors)
        complete = len(response.pairs) == count
        span.set_attribute("kessel.allowed", complete and allowed_count == count)
        # Match HBI's fail-closed result, while response counts describe what Kessel sent.
        span.set_attribute("kessel.denied_count", len(response.pairs) - allowed_count if complete else count)
        span.set_attribute("kessel.response.complete", complete)
        span.set_attribute("kessel.response.count", len(response.pairs))
        span.set_attribute("kessel.response.allowed_count", allowed_count)
        span.set_attribute("kessel.response.denied_count", denied_count)
        span.set_attribute("kessel.response.indeterminate_count", indeterminate_count)
        span.set_attribute("kessel.response.error_count", len(errors))
        if errors:
            codes = sorted(set(errors))
            span.set_attribute("kessel.response.error_codes", codes)
            span.set_attribute(
                "kessel.response.error_status_names", [_GRPC_STATUS_NAMES.get(c, "UNRECOGNIZED") for c in codes]
            )
        if not complete:
            _response_error(span, "KesselIncompleteResponse")
        elif errors:
            _response_error(span, "KesselBulkItemError")
        elif indeterminate_count:
            _response_error(span, "KesselIndeterminateDecision")
    elif hasattr(response, "allowed"):
        span.set_attribute("kessel.allowed", response.allowed == allowed_pb2.ALLOWED_TRUE)
        span.set_attribute("kessel.response.complete", True)
        try:
            allowed = allowed_pb2.Allowed.Name(response.allowed)
        except ValueError:
            allowed = "ALLOWED_UNRECOGNIZED"
        span.set_attribute("kessel.response.allowed", allowed)
        if response.allowed not in (allowed_pb2.ALLOWED_TRUE, allowed_pb2.ALLOWED_FALSE):
            _response_error(span, "KesselIndeterminateDecision")


def _response_error(span, error_type):
    span.set_attribute("error.type", error_type)
    span.set_status(trace.StatusCode.ERROR)


class _WorkspaceContextInterceptor(grpcext.StreamClientInterceptor):
    def intercept_stream(self, request, metadata, client_info, invoker):
        # The outer standard interceptor has already activated the client span.
        if not is_instrumentation_enabled() or not client_info.full_method.endswith("/StreamedListObjects"):
            yield from invoker(request, metadata)
            return
        span = trace.get_current_span()
        _request_hook(span, request)
        count = 0
        try:
            for response in invoker(request, metadata):
                count += 1
                yield response
            span.set_attribute("kessel.response.complete", True)
        finally:
            # Preserve partial response counts if Kessel fails during streaming.
            span.set_attribute("kessel.resource_count", count)
            span.set_attribute("kessel.response.count", count)


def instrument_channel(channel, target: str):
    interceptor = client_interceptor(
        tracer_provider=_SafeTracerProvider(trace.get_tracer_provider(), target),
        request_hook=_request_hook,
        response_hook=_response_hook,
    )
    return grpcext.intercept_channel(channel, _WorkspaceContextInterceptor(), interceptor)
