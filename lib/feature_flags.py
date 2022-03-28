from flask_unleash import Unleash

UNLEASH = Unleash()
FLAG_HIDE_EDGE_BY_DEFAULT = "hbi.api-hide-edge-default"


def init_unleash_app(app):
    UNLEASH.init_app(app)
