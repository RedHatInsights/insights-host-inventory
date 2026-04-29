"""
OpenTelemetry instrumentation helpers for Insights Host Inventory.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status
from opentelemetry.trace import StatusCode

from app.logging import get_logger
from app.otel_config import get_tracer

logger = get_logger(__name__)


def trace_host_operation(
    operation_name: str,
    extract_host_id: Callable | None = None,
    extract_org_id: Callable | None = None,
    extract_reporter: Callable | None = None,
):
    """
    Decorator to trace host operations with automatic span creation and attribute setting.

    Args:
        operation_name: Name of the operation for the span
        extract_host_id: Function to extract host ID from the operation arguments
        extract_org_id: Function to extract org ID from the operation arguments
        extract_reporter: Function to extract reporter from the operation arguments
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer(__name__)

            with tracer.start_as_current_span(f"inventory.{operation_name}", kind=trace.SpanKind.INTERNAL) as span:
                try:
                    # Set basic span attributes
                    span.set_attribute("operation.name", operation_name)
                    span.set_attribute("service.name", "insights-host-inventory")

                    # Extract and set host-specific attributes
                    if extract_host_id:
                        try:
                            host_id = extract_host_id(*args, **kwargs)
                            if host_id:
                                span.set_attribute("host.id", str(host_id))
                        except Exception as e:
                            logger.debug("Failed to extract host_id for tracing: %s", e)

                    if extract_org_id:
                        try:
                            org_id = extract_org_id(*args, **kwargs)
                            if org_id:
                                span.set_attribute("host.org_id", str(org_id))
                        except Exception as e:
                            logger.debug("Failed to extract org_id for tracing: %s", e)

                    if extract_reporter:
                        try:
                            reporter = extract_reporter(*args, **kwargs)
                            if reporter:
                                span.set_attribute("host.reporter", str(reporter))
                        except Exception as e:
                            logger.debug("Failed to extract reporter for tracing: %s", e)

                    # Execute the wrapped function
                    result = func(*args, **kwargs)

                    # Mark span as successful
                    span.set_status(Status(StatusCode.OK))

                    return result

                except Exception as e:
                    # Record the exception and mark span as error
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        return wrapper

    return decorator


def trace_mq_message_processing(operation_name: str):
    """
    Decorator specifically for message queue processing operations.

    Args:
        operation_name: Name of the MQ operation
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer(__name__)

            with tracer.start_as_current_span(f"inventory.mq.{operation_name}", kind=trace.SpanKind.CONSUMER) as span:
                try:
                    # Set message processing attributes
                    span.set_attribute("messaging.system", "kafka")
                    span.set_attribute("messaging.operation", operation_name)
                    span.set_attribute("service.name", "insights-host-inventory")

                    # Try to extract message information from args
                    if args and hasattr(args[0], "__class__"):
                        span.set_attribute("consumer.class", args[0].__class__.__name__)

                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        return wrapper

    return decorator


def add_span_attributes(attributes: dict[str, Any]) -> None:
    """
    Add attributes to the current active span.

    Args:
        attributes: Dictionary of attributes to add to the span
    """
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        for key, value in attributes.items():
            if value is not None:
                current_span.set_attribute(key, str(value))


def record_host_operation_result(result: Any, host_data: dict | None = None) -> None:
    """
    Record the result of a host operation in the current span.

    Args:
        result: The result of the operation (e.g., AddHostResult enum)
        host_data: Optional host data dictionary
    """
    current_span = trace.get_current_span()
    if not current_span or not current_span.is_recording():
        return

    try:
        # Record operation result
        if hasattr(result, "name"):
            current_span.set_attribute("operation.result", result.name)
        else:
            current_span.set_attribute("operation.result", str(result))

        # Record host information if available
        if host_data:
            if "id" in host_data:
                current_span.set_attribute("host.id", str(host_data["id"]))
            if "org_id" in host_data:
                current_span.set_attribute("host.org_id", str(host_data["org_id"]))
            if "reporter" in host_data:
                current_span.set_attribute("host.reporter", str(host_data["reporter"]))
            if "account" in host_data:
                current_span.set_attribute("host.account", str(host_data["account"]))

    except Exception as e:
        logger.debug("Failed to record host operation result in span: %s", e)


def trace_batch_operation(batch_size: int) -> None:
    """
    Add batch operation attributes to the current span.

    Args:
        batch_size: Size of the batch being processed
    """
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute("batch.size", batch_size)
        current_span.set_attribute("operation.type", "batch")


def create_child_span(name: str, kind: trace.SpanKind = trace.SpanKind.INTERNAL):
    """
    Create a child span with the given name.

    Args:
        name: Name of the span
        kind: Kind of span (INTERNAL, CLIENT, SERVER, etc.)

    Returns:
        Span context manager
    """
    tracer = get_tracer(__name__)
    return tracer.start_as_current_span(name, kind=kind)


# Extraction functions for common host operation patterns
def extract_host_id_from_args(*args, **kwargs) -> str | None:
    """Extract host ID from function arguments."""
    # Check for host object in args
    for arg in args:
        if hasattr(arg, "id"):
            return str(arg.id)
        if isinstance(arg, dict) and "id" in arg:
            return str(arg["id"])

    # Check kwargs
    if "host_id" in kwargs:
        return str(kwargs["host_id"])
    if "host" in kwargs and hasattr(kwargs["host"], "id"):
        return str(kwargs["host"].id)

    return None


def extract_org_id_from_args(*args, **kwargs) -> str | None:
    """Extract org ID from function arguments."""
    # Check for host object in args
    for arg in args:
        if hasattr(arg, "org_id"):
            return str(arg.org_id)
        if isinstance(arg, dict) and "org_id" in arg:
            return str(arg["org_id"])

    # Check kwargs
    if "org_id" in kwargs:
        return str(kwargs["org_id"])
    if "identity" in kwargs and hasattr(kwargs["identity"], "org_id"):
        return str(kwargs["identity"].org_id)

    return None


def extract_reporter_from_args(*args, **kwargs) -> str | None:
    """Extract reporter from function arguments."""
    # Check for host object in args
    for arg in args:
        if hasattr(arg, "reporter"):
            return str(arg.reporter)
        if isinstance(arg, dict) and "reporter" in arg:
            return str(arg["reporter"])

    # Check kwargs
    if "reporter" in kwargs:
        return str(kwargs["reporter"])

    return None
