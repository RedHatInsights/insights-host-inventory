from __future__ import annotations

import asyncio

import pytest
from connexion import FlaskApp
from sqlalchemy import text

from app.models import db
from tests.helpers.sql_dump import dumps_sql


def _joined_output(write_calls: list[str]) -> str:
    return "".join(write_calls)


def test_dumps_sql_sync_function_logs_sql(flask_app: FlaskApp) -> None:
    with flask_app.app.app_context():
        chunks: list[str] = []

        @dumps_sql(write_method=chunks.append)
        def run_query():
            db.session.execute(text("SELECT 1 AS x"))
            db.session.commit()

        run_query()
        assert "**** QUERY:" in _joined_output(chunks)


def test_dumps_sql_generator_logs_sql_during_iteration(flask_app: FlaskApp) -> None:
    with flask_app.app.app_context():
        chunks: list[str] = []

        @dumps_sql(write_method=chunks.append)
        def gen_queries():
            db.session.execute(text("SELECT 1 AS a"))
            yield 1
            db.session.execute(text("SELECT 2 AS b"))

        g = gen_queries()
        assert next(g) == 1
        with pytest.raises(StopIteration):
            next(g)

        out = _joined_output(chunks)
        assert out.count("**** QUERY:") >= 2


def test_dumps_sql_async_function_logs_sql(flask_app: FlaskApp) -> None:
    with flask_app.app.app_context():
        chunks: list[str] = []

        @dumps_sql(write_method=chunks.append)
        async def run_query():
            db.session.execute(text("SELECT 3 AS c"))
            db.session.commit()

        asyncio.run(run_query())
        assert "**** QUERY:" in _joined_output(chunks)


def test_dumps_sql_async_generator_logs_sql_during_iteration(flask_app: FlaskApp) -> None:
    with flask_app.app.app_context():
        chunks: list[str] = []

        @dumps_sql(write_method=chunks.append)
        async def gen_queries():
            db.session.execute(text("SELECT 1 AS a"))
            yield 1
            db.session.execute(text("SELECT 2 AS b"))

        async def consume() -> None:
            async for _ in gen_queries():
                pass

        asyncio.run(consume())
        assert _joined_output(chunks).count("**** QUERY:") >= 2


def test_dumps_sql_honors_custom_dump_method(flask_app: FlaskApp) -> None:
    with flask_app.app.app_context():
        markers: list[str] = []

        def custom_dump(*_args):
            markers.append("dump")

        @dumps_sql(dump_method=custom_dump, write_method=lambda *_: None)
        def run_query():
            db.session.execute(text("SELECT 1"))
            db.session.commit()

        run_query()
        assert markers == ["dump"]


def test_dumps_sql_sync_removes_listener_after_exception(flask_app: FlaskApp) -> None:
    with flask_app.app.app_context():
        chunks: list[str] = []

        @dumps_sql(write_method=chunks.append)
        def boom():
            db.session.execute(text("SELECT 1"))
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError, match="fail"):
            boom()

        logged = len(chunks)
        assert logged > 0

        db.session.execute(text("SELECT 2"))
        assert len(chunks) == logged
