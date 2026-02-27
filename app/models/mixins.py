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
        Derive host_type from host and system profile data.

        This is the single source of truth for host_type derivation, used by both
        SQLAlchemy models (Host/LimitedHost) and dict-based wrappers (HostWrapper).

        Business logic:
        - CLUSTER: openshift_cluster_id is set, OR host_type == "cluster" (explicit)
        - EDGE: host_type == "edge" (explicit)
        - BOOTC: bootc_status["booted"]["image_digest"] is not None/empty
        - CONVENTIONAL: default fallback

        Priority order:
        1. Check openshift_cluster_id - if present, return "cluster"
        2. Use explicit host_type from system profile if set ("edge" or "cluster")
        3. Check bootc_status for bootc systems (bootc_status["booted"]["image_digest"] is not None/empty)
        4. Default to "conventional" (traditional systems)

        Returns:
            str: The derived host type ('cluster', 'edge', 'bootc', or 'conventional')
        """
        # Check openshift_cluster_id first - this takes priority
        if getattr(self, "openshift_cluster_id", None):
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
