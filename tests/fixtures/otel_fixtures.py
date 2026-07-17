"""Pytest fixtures for OpenTelemetry test isolation."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.test.globals_test import reset_trace_globals


@pytest.fixture()
def otel_provider():
    """Factory fixture that creates an isolated TracerProvider + InMemorySpanExporter.

    Usage (local provider, no global state):

        def test_something(otel_provider):
            provider, exporter = otel_provider()
            tracer = provider.get_tracer("test")
            ...

    With extra span processors prepended before the exporter:

        def test_processor(otel_provider):
            provider, exporter = otel_provider(span_processors=[my_processor])
            ...

    With global registration (for instrumentation libs that read the global provider):

        def test_flask(otel_provider):
            provider, exporter = otel_provider(set_global=True)
            ...
    """
    providers = []

    def _factory(*, span_processors=None, set_global=False, **provider_kwargs):
        provider_kwargs.setdefault("resource", Resource.create())
        provider = TracerProvider(**provider_kwargs)
        exporter = InMemorySpanExporter()

        for sp in span_processors or []:
            provider.add_span_processor(sp)
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        if set_global:
            reset_trace_globals()
            trace.set_tracer_provider(provider)

        providers.append((provider, set_global))
        return provider, exporter

    yield _factory

    for provider, _ in providers:
        provider.shutdown()
    if any(was_global for _, was_global in providers):
        reset_trace_globals()
