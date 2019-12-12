import flask
import ujson


def json_response(json_data, status=200):
    return flask.Response(ujson.dumps(json_data), status=status, mimetype="application/json")


def build_collection_response(data, page, per_page, total, count):
    return {"total": total, "count": count, "page": page, "per_page": per_page, "results": data}
