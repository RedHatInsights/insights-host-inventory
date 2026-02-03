"""
Mixin classes for host-related functionality.

This module is kept separate to avoid circular imports between app.models.host and app.utils.
"""


class HostTypeDeriver:
    """
    Mixin class that provides host_type derivation logic.

    Works with both SQLAlchemy models (using static_system_profile relationship)
    and dict-based wrappers (using system_profile dict).
    """

    def _get_system_profile_data(self) -> dict:
        """
        Get system profile data as a dict.

        Subclasses can override this if they store system profile differently.
        """
        # For SQLAlchemy models with static_system_profile relationship
        if hasattr(self, "static_system_profile") and self.static_system_profile is not None:
            static = self.static_system_profile
            return {
                "host_type": getattr(static, "host_type", None),
                "bootc_status": getattr(static, "bootc_status", None),
            }

        # For dict-based wrappers with system_profile dict
        if hasattr(self, "system_profile"):
            sp = self.system_profile
            if isinstance(sp, dict):
                return sp

        return {}

    def derive_host_type(self) -> str:
        """
        Derive host_type from system profile data.

        Business logic:
        - EDGE: host_type == "edge" (explicit)
        - CLUSTER: host_type == "cluster" (explicit)
        - BOOTC: bootc_status exists AND bootc_status["booted"]["image_digest"] is not None/empty
        - CONVENTIONAL: default (bootc_status is None/empty OR image_digest is None/empty, AND host_type is None/empty)

        Priority order:
        1. Use explicit host_type from system profile if set ("edge" or "cluster")
        2. Check bootc_status for bootc systems (bootc_status["booted"]["image_digest"] is not None/empty)
        3. Default to "conventional" (traditional systems)

        Returns:
            str: The derived host type ('cluster', 'edge', 'bootc', or 'conventional')
        """

        if self.openshift_cluster_id:  # type: ignore[attr-defined]
            return "cluster"

        system_profile = self._get_system_profile_data()

        if not system_profile:
            return "conventional"

        host_type = system_profile.get("host_type")
        if host_type in {"edge", "cluster"}:
            return host_type

        bootc_status = system_profile.get("bootc_status") or {}

        if isinstance(bootc_status, dict):
            image_digest = bootc_status.get("booted", {}).get("image_digest")

            if image_digest:
                return "bootc"

        return "conventional"
