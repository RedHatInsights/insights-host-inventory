"""Classify Connexion HTTP exceptions on library-owned Flask request spans."""

from connexion.exceptions import ProblemException
from opentelemetry import trace
from starlette.exceptions import HTTPException
from wrapt import ObjectProxy


class _HTTPSpan(ObjectProxy):
    def __init__(self, span):
        super().__init__(span)
        self._self_client_error = False

    def record_exception(self, exception, *args, **kwargs):
        if isinstance(exception, HTTPException):
            status_code = exception.status_code
        elif isinstance(exception, ProblemException):
            status_code = exception.status
        else:
            status_code = None

        self._self_client_error = status_code is not None and 400 <= status_code < 500
        if status_code is not None:
            # Connexion builds the response outside Flask, so start_response
            # never runs. Record the status before Flask ends the span.
            self.__wrapped__.set_attribute("http.status_code", status_code)
        if not self._self_client_error:
            self.__wrapped__.record_exception(exception, *args, **kwargs)

    def set_status(self, status, description=None):
        code = status.status_code if isinstance(status, trace.Status) else status
        # use_span records the exception before setting ERROR during teardown.
        # Expected HTTP client errors should retain UNSET and no exception event.
        if self._self_client_error and code == trace.StatusCode.ERROR:
            return
        self.__wrapped__.set_status(status, description)


class _HTTPTracer(ObjectProxy):
    def start_span(self, *args, **kwargs):
        return _HTTPSpan(self.__wrapped__.start_span(*args, **kwargs))


class HTTPTracerProvider(ObjectProxy):
    """Adapt Flask spans without changing Connexion's exception handlers."""

    def get_tracer(self, *args, **kwargs):
        return _HTTPTracer(self.__wrapped__.get_tracer(*args, **kwargs))
