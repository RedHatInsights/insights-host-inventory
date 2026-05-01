from http import HTTPStatus

from flask import abort


def get_views_list(**kwargs):  # noqa: ARG001
    abort(HTTPStatus.NOT_IMPLEMENTED)


def create_view(body, **kwargs):  # noqa: ARG001
    abort(HTTPStatus.NOT_IMPLEMENTED)


def get_view_by_id(view_id, **kwargs):  # noqa: ARG001
    abort(HTTPStatus.NOT_IMPLEMENTED)


def update_view(view_id, body, **kwargs):  # noqa: ARG001
    abort(HTTPStatus.NOT_IMPLEMENTED)


def delete_view(view_id, **kwargs):  # noqa: ARG001
    abort(HTTPStatus.NOT_IMPLEMENTED)


def clone_view(view_id, **kwargs):  # noqa: ARG001
    abort(HTTPStatus.NOT_IMPLEMENTED)
