from app.auth import bypass_auth


__all__ = ["health"]


@bypass_auth
def health():
    return "", 200
