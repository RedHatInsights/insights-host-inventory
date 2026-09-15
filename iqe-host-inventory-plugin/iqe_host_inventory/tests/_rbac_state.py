# Module-level flag set when RBAC pre-configured role setup fails
# during the session-scoped autouse fixture.  Non-RBAC tests continue
# running; RBAC-dependent tests check this flag and skip themselves.
rbac_setup_failed: str | None = None  # None = success, str = error message
