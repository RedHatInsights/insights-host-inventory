"""
Lightweight request profiling — enable via INVENTORY_PROFILING_ENABLED=true.

Monkey-patches key functions and hooks into SQLAlchemy events to accumulate
per-request timing, then logs a summary line in after_request.
Zero overhead when disabled.

Add to your app setup:
    from api.profiling import init_profiling
    init_profiling(flask_app)
"""

import os
import time
from functools import wraps

from flask import g

from app.logging import get_logger

logger = get_logger("profiling")


def _is_enabled():
    return os.getenv("INVENTORY_PROFILING_ENABLED", "false").lower() == "true"


def _timer(label):
    """Decorator that records call duration under g._prof[label]."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            t0 = time.perf_counter()
            try:
                return fn(*a, **kw)
            finally:
                elapsed = time.perf_counter() - t0
                prof = getattr(g, "_prof", None)
                if prof is not None:
                    prev_total, prev_count = prof.get(label, (0.0, 0))
                    prof[label] = (prev_total + elapsed, prev_count + 1)

        return wrapper

    return decorator


def _install_sqlalchemy_timing():
    """Track cumulative DB time per request via SQLAlchemy engine events."""
    from sqlalchemy import event

    from app.models.database import db

    engine = db.engine

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        conn.info.setdefault("query_start_time", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        start_stack = conn.info.get("query_start_time")
        if not start_stack:
            return
        elapsed = time.perf_counter() - start_stack.pop()
        prof = getattr(g, "_prof", None)
        if prof is not None:
            prev_total, prev_count = prof.get("db", (0.0, 0))
            prof["db"] = (prev_total + elapsed, prev_count + 1)


def init_profiling(flask_app):
    if not _is_enabled():
        logger.info("Request profiling disabled (INVENTORY_PROFILING_ENABLED != true)")
        return

    logger.debug("Request profiling ENABLED — expect minor overhead")

    # --- Imports ---
    import api.filtering.db_filters as dbf
    import api.host as ah
    import api.host_query as hq
    import api.host_views as hv
    import api.staleness as ast
    import api.staleness_query as sq
    import app.serialization
    import lib.middleware as mw
    from app.serialization import serialize_host as _orig_ser

    # --- Patch staleness ---
    patched_staleness = _timer("staleness")(sq.get_staleness_obj)
    sq.get_staleness_obj = patched_staleness
    hq.get_staleness_obj = patched_staleness
    ah.get_staleness_obj = patched_staleness
    hv.get_staleness_obj = patched_staleness
    dbf.get_staleness_obj = patched_staleness

    # --- Patch auth ---
    mw.get_rbac_filter = _timer("rbac_v1")(mw.get_rbac_filter)
    mw.get_kessel_filter = _timer("kessel")(mw.get_kessel_filter)

    # --- Patch serialization ---
    patched_ser = _timer("serialize")(_orig_ser)
    app.serialization.serialize_host = patched_ser
    hq.serialize_host = patched_ser
    ah.serialize_host = patched_ser
    hv.serialize_host = patched_ser
    ast.serialize_host = patched_ser

    # --- Patch feature flags ---
    try:
        import lib.feature_flags as ff

        patched_flag = _timer("unleash")(ff.get_flag_value)
        ff.get_flag_value = patched_flag
        mw.get_flag_value = patched_flag
    except Exception:
        pass

    # --- Request hooks ---
    app = flask_app.app if hasattr(flask_app, "app") else flask_app

    _sa_installed = False

    @app.before_request
    def _prof_start():
        nonlocal _sa_installed
        if not _sa_installed:
            try:
                _install_sqlalchemy_timing()
                logger.info("SQLAlchemy query timing installed")
            except Exception:
                logger.exception("Failed to install SQLAlchemy query timing")
            _sa_installed = True

        g._prof = {}
        g._prof_t0 = time.perf_counter()

    @app.after_request
    def _prof_log(response):
        prof = getattr(g, "_prof", None)
        t0 = getattr(g, "_prof_t0", None)
        if prof is None or t0 is None:
            return response

        total = time.perf_counter() - t0

        db_total, db_count = prof.pop("db", (0.0, 0))

        parts = " | ".join(f"{k}={v[0] * 1000:.1f}ms(x{v[1]})" for k, v in sorted(prof.items()) if v[0] > 0.0005)
        accounted = sum(v[0] for v in prof.values())
        unaccounted = total - accounted - db_total

        from flask import request

        logger.debug(
            "PROF %s %s total=%.1fms [ %s | db=%.1fms(x%d) | other=%.1fms ] status=%s",
            request.method,
            request.path,
            total * 1000,
            parts,
            db_total * 1000,
            db_count,
            unaccounted * 1000,
            response.status_code,
        )
        return response
