# utility functions.
# previously staleness defaults were set in api.spec but that caused problems filtering hosts using stateless.
def staleness_defaults():
    return ["fresh", "stale", "unknown"]
