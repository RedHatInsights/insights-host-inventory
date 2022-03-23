from flask_unleash import Unleash

UNLEASH = Unleash()


def init_unleash_app(app):
    UNLEASH.init_app(app)


def unleash_default_value(feature_name: str, context: dict) -> bool:
    return f"Unable to retrieve value for {feature_name} from Unleash; using default value"
