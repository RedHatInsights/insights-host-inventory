import logging
from functools import cached_property
from time import sleep

import attr
import pytest
from iqe.base.feature_flags import get_feature_flag_backend
from iqe.base.feature_flags.consoledot_proxy import ConsoleDotProxyBackend
from iqe.base.feature_flags.unleash import UnleashBackend
from iqe.base.feature_flags.unleash import UnleashFlagRequest
from iqe.base.feature_flags.unleash import _RequestType
from iqe.base.modeling import BaseEntity

logger = logging.getLogger(__name__)


@attr.s
class HBIUnleash(BaseEntity):
    @cached_property
    def _unleash(self) -> UnleashBackend | ConsoleDotProxyBackend:
        if self.application.config.current_env in ["ephemeral", "clowder_smoke"]:
            unleash = get_feature_flag_backend("unleash", self.application)
        else:
            unleash = self.application.feature_flag

        return unleash

    def toggle_feature_flag(self, flag: str, enable: bool = True):
        """Help function to toggle feature flag.

        Toggling a feature flag is possible only in ephemeral environments.
        In the stage/prod environment, this function checks the value of the flag.
        If it is different from the `enable` parameter, it skips the test.

        """
        if isinstance(self._unleash, UnleashBackend):
            logger.info(f"Switching '{flag}' feature flag to: {enable}")
            if enable:
                self._unleash.admin.enable_flag(flag)
            else:
                self._unleash.admin.disable_flag(flag)
            sleep(1.5)  # HBI Unleash cache gets refreshed every second in ephemeral
        elif isinstance(self._unleash, ConsoleDotProxyBackend):
            if enable == self._unleash.is_enabled(flag):
                logger.info(f"'{flag}' feature flag already set to: {enable}.")
            else:
                pytest.xfail(
                    f"'{flag}' feature flag is set to {not enable} in current environment."
                )

    @cached_property
    def kessel_phase_1_flag(self) -> str:
        feature_flag = "hbi.api.kessel-phase-1"

        if isinstance(self._unleash, UnleashBackend) and not self._unleash.has_flag(feature_flag):
            flag_request = UnleashFlagRequest(
                name=feature_flag,
                description="kessel_phase_1 flag",
                type=_RequestType.RELEASE,
                impressionData=False,
            )
            self._unleash.admin.create_flag(flag_request=flag_request)

        return feature_flag

    @cached_property
    def kessel_groups_flag(self) -> str:
        feature_flag = "hbi.api.kessel-groups"

        if isinstance(self._unleash, UnleashBackend) and not self._unleash.has_flag(feature_flag):
            flag_request = UnleashFlagRequest(
                name=feature_flag,
                description="RBAC v2 workspace support for groups endpoints",
                type=_RequestType.RELEASE,
                impressionData=False,
            )
            self._unleash.admin.create_flag(flag_request=flag_request)

        return feature_flag

    def is_flag_enabled(self, flag: str) -> bool:
        return self._unleash.is_enabled(flag)

    def is_kessel_phase_1_enabled(self) -> bool:
        return self.is_flag_enabled(self.kessel_phase_1_flag)

    def is_kessel_groups_enabled(self) -> bool:
        return self.is_flag_enabled(self.kessel_groups_flag)
