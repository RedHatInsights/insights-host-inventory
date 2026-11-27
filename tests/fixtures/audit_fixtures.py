"""Capture actual formatted audit output without leaking context between tests."""

import logging
from io import StringIO

import pytest

from app import audit
from app.logging import threadctx


@pytest.fixture
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
