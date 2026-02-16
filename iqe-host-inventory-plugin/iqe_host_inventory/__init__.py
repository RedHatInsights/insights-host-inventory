from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import attr
from iqe.base.application.plugins import ApplicationPlugin
from iqe.base.application.plugins import ApplicationPluginException
from iqe.base.application.plugins.service_objects import RESTPluginService

if TYPE_CHECKING:
    from . import modeling
    from .modeling import kafka_interaction
    from .modeling import unleash
    from .modeling import uploads


class ApplicationHostInventoryException(ApplicationPluginException):
    """Basic Exception for host_inventory object"""


@attr.s
class ApplicationHostInventory(ApplicationPlugin):
    """Holder for application host_inventory related methods and functions"""

    tags = ("host_inventory", "platform", "platform-inventory")

    plugin_real_name = "Host Inventory"
    plugin_name = "host_inventory"
    plugin_title = "HostInventory"
    plugin_package_name = "iqe-host-inventory-plugin"
    rest_client = RESTPluginService.declare("api")

    api_v7 = RESTPluginService.declare("api_v7")

    @cached_property
    def datagen(self) -> kafka_interaction.HBIKafkaDatagen:
        from .modeling import kafka_interaction

        return kafka_interaction.HBIKafkaDatagen(self)

    @cached_property
    def apis(self) -> modeling.HBIApis:
        from . import modeling

        return modeling.HBIApis(self)

    @cached_property
    def database(self) -> modeling.HBIDatabase:
        from . import modeling

        return modeling.HBIDatabase(self)

    @cached_property
    def upload(self) -> uploads.HBIUploads:
        from .modeling import uploads

        return uploads.HBIUploads(self)

    @cached_property
    def kafka(self) -> kafka_interaction.HBIKafkaActions:
        from .modeling import kafka_interaction

        return kafka_interaction.HBIKafkaActions(self)

    @cached_property
    def cleanup(self) -> modeling.HBICleanUp:
        from . import modeling

        return modeling.HBICleanUp(self)

    @cached_property
    def unleash(self) -> unleash.HBIUnleash:
        from .modeling import unleash

        return unleash.HBIUnleash(self)
