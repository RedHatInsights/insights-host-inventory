# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import cached_property

from iqe.base.http import RobustSession
from kessel.relations.v1beta1.common_pb2 import Relationship
from kessel.relations.v1beta1.relation_tuples_pb2 import ReadTuplesRequest
from kessel.relations.v1beta1.relation_tuples_pb2 import ReadTuplesResponse
from kessel.relations.v1beta1.relation_tuples_pb2 import RelationTupleFilter
from kessel.relations.v1beta1.relation_tuples_pb2 import SubjectFilter
from kessel.relations.v1beta1.relation_tuples_pb2_grpc import KesselTupleServiceStub
from requests.models import Response

from iqe_host_inventory.modeling.groups_api import GROUP_OR_ID
from iqe_host_inventory.modeling.groups_api import _id_from_group
from iqe_host_inventory.modeling.hosts_api import HOST_OR_ID
from iqe_host_inventory.modeling.hosts_api import _id_from_host
from iqe_host_inventory.utils.api_utils import accept_when

HOST_NOT_SYNCED_ERROR = Exception("Host changes weren't successfully synced to Kessel Relations")

EPHEMERAL_ENVS = ("clowder_smoke", "ephemeral", "smoke")

logger = logging.getLogger(__name__)


def camel_to_snake(name):
    """Convert a camelCase string to snake_case."""
    # Insert underscore before uppercase letters and convert to lowercase
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def convert_keys_to_snake_case(obj):
    """Recursively convert all dictionary keys from camelCase to snake_case."""
    if isinstance(obj, dict):
        return {
            camel_to_snake(key): convert_keys_to_snake_case(value) for key, value in obj.items()
        }
    elif isinstance(obj, list):
        return [convert_keys_to_snake_case(item) for item in obj]
    else:
        return obj


def filter_to_dict(filter: RelationTupleFilter) -> dict[str, str]:
    return {
        "resource_namespace": filter.resource_namespace,
        "resource_type": filter.resource_type,
        "resource_id": filter.resource_id,
        "relation": filter.relation,
        "subject_filter": {
            "subject_namespace": filter.subject_filter.subject_namespace,
            "subject_type": filter.subject_filter.subject_type,
            "subject_id": filter.subject_filter.subject_id,
        },
    }


@dataclass(order=False)
class HostWorkspaceRelationWrapper:
    host_id: str
    workspace_id: str

    @classmethod
    def from_tuple(cls, relation_tuple: Relationship) -> HostWorkspaceRelationWrapper:
        return cls(
            host_id=relation_tuple.resource.id, workspace_id=relation_tuple.subject.subject.id
        )


class HBIKesselRelationsGRPC:
    """Example Host/Workspace relation 'tuple':
    {
        type {
            namespace: "hbi"
            name: "host"
        }
        id: "fcee333f-08e9-4945-ba99-11da5017d49a"  # host_id
    }
    relation: "workspace"
    subject {
        subject {
            type {
                namespace: "rbac"
                name: "workspace"
            }
            id: "019a100c-7a38-7231-96d5-c1b34a4be31d"  # workspace_id
        }
    }
    """

    def __init__(
        self,
        *,
        env: str,
        grpc_service: KesselTupleServiceStub | None = None,
        turnpike_http_client: RobustSession | None = None,
        turnpike_base_url: str | None = None,
    ):
        self.env = env
        self.grpc_service = grpc_service
        self.turnpike_http_client = turnpike_http_client
        self.turnpike_base_url = turnpike_base_url

    @cached_property
    def is_grpc_env(self) -> bool:
        return self.env.lower() in EPHEMERAL_ENVS

    def read_tuples_turnpike_response(self, filter: RelationTupleFilter) -> Response:
        filter_dict = filter_to_dict(filter)
        logger.info(
            f"Reading tuples from Kessel Relations via Turnpike with filter:\n{filter_dict}"
        )
        return self.turnpike_http_client.post(
            f"{self.turnpike_base_url}/relations/read_tuples/", json={"filter": filter_dict}
        )

    def read_tuples_turnpike(self, filter: RelationTupleFilter) -> list[Relationship]:
        # Turnpike returns camelCase keys, so we need to convert them to snake_case
        tuples: list[dict] = convert_keys_to_snake_case(
            self.read_tuples_turnpike_response(filter).json()["tuples"]
        )
        grpc_responses = [
            ReadTuplesResponse(
                tuple=tuple["tuple"],
                pagination=tuple["pagination"],
                consistency_token=tuple["consistency_token"],
            )
            for tuple in tuples
        ]
        return [response.tuple for response in grpc_responses]

    def read_tuples_grpc_response(self, filter: RelationTupleFilter) -> list[ReadTuplesResponse]:
        logger.info(f"Reading tuples from Kessel Relations via gRPC with filter:\n{filter}")
        return list(self.grpc_service.ReadTuples(ReadTuplesRequest(filter=filter)))

    def read_tuples_grpc(self, filter: RelationTupleFilter) -> list[Relationship]:
        return [response.tuple for response in self.read_tuples_grpc_response(filter)]

    def get_host_workspace_tuples_raw(
        self, host: HOST_OR_ID | None = None, workspace: GROUP_OR_ID | None = None
    ) -> list[Relationship]:
        host_id = _id_from_host(host) if host is not None else None
        workspace_id = _id_from_group(workspace) if workspace is not None else None

        filter = RelationTupleFilter(
            resource_namespace="hbi",
            resource_type="host",
            relation="workspace",
            subject_filter=SubjectFilter(subject_namespace="rbac", subject_type="workspace"),
        )
        if host_id is not None:
            filter.resource_id = host_id
        if workspace_id is not None:
            filter.subject_filter.subject_id = workspace_id

        if self.is_grpc_env:
            return self.read_tuples_grpc(filter)
        return self.read_tuples_turnpike(filter)

    def get_host_workspace_tuples(
        self, host: HOST_OR_ID | None = None, workspace: GROUP_OR_ID | None = None
    ) -> list[HostWorkspaceRelationWrapper]:
        return [
            HostWorkspaceRelationWrapper.from_tuple(relation_tuple)
            for relation_tuple in self.get_host_workspace_tuples_raw(host, workspace)
        ]

    def get_host_workspace_tuple(
        self, host: HOST_OR_ID, workspace: GROUP_OR_ID | None = None
    ) -> HostWorkspaceRelationWrapper | None:
        tuples = self.get_host_workspace_tuples(host=host, workspace=workspace)
        assert len(tuples) <= 1, f"One host can never be in more than one workspace, got: {tuples}"
        return tuples[0] if tuples else None

    def verify_created_or_updated(
        self,
        host: HOST_OR_ID,
        workspace: GROUP_OR_ID,
        *,
        delay: float = 0.5,
        retries: int = 30,
        error: Exception | None = HOST_NOT_SYNCED_ERROR,
    ) -> HostWorkspaceRelationWrapper | None:
        """Wait until the host changes are successfully synced to Kessel Relations

        :param HOST_OR_ID host: (required) A single host
            A host can be represented either by its ID (str) or a host object
        :param GROUP_OR_ID workspace: (required) A single workspace
            A workspace can be represented either by its ID (str) or a workspace object
        :param float delay: A delay in seconds between attempts to retrieve the relation
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the host/workspace relation
            Default: 30
        :param Exception error: An error to raise when the relation is not retrievable. If `None`,
            then no error will be raised and the method will finish successfully.
        :return HostWorkspaceRelationWrapper | None: Retrieved host/workspace relation
        """
        host_id = _id_from_host(host)
        workspace_id = _id_from_group(workspace)

        def get_tuple() -> HostWorkspaceRelationWrapper | None:
            return self.get_host_workspace_tuple(host=host_id, workspace=workspace_id)

        def host_changes_synced(response_tuple: HostWorkspaceRelationWrapper | None) -> bool:
            if response_tuple is None:
                return False

            # The following assertions should never fail,
            # but are included in case the filtering doesn't work correctly.
            assert response_tuple.host_id == host_id
            assert response_tuple.workspace_id == workspace_id

            return True

        return accept_when(
            get_tuple, is_valid=host_changes_synced, delay=delay, retries=retries, error=error
        )

    def verify_deleted(
        self,
        host: HOST_OR_ID,
        *,
        delay: float = 0.5,
        retries: int = 30,
        error: Exception | None = HOST_NOT_SYNCED_ERROR,
    ) -> HostWorkspaceRelationWrapper | None:
        """Wait until the host is successfully deleted from Kessel Relations

        :param HOST_OR_ID host: (required) A single host
            A host can be represented either by its ID (str) or a host object
        :param float delay: A delay in seconds between attempts to check that the host is deleted
            Default: 0.5
        :param int retries: A maximum number of attempts to check that the host is deleted
            Default: 30
        :param Exception error: An error to raise when the relation is not retrievable. If `None`,
            then no error will be raised and the method will finish successfully.
        :return HostWorkspaceRelationWrapper | None: Retrieved relation if the host is not deleted
        """

        def get_tuple() -> HostWorkspaceRelationWrapper | None:
            return self.get_host_workspace_tuple(host=host)

        def host_deleted(response_tuple: HostWorkspaceRelationWrapper | None) -> bool:
            if response_tuple is not None:
                logger.info(
                    "This host is not yet deleted from Kessel Relations:\n"
                    f"Host ID: {response_tuple.host_id}\n"
                    f"Workspace ID: {response_tuple.workspace_id}"
                )
            return response_tuple is None

        return accept_when(
            get_tuple, is_valid=host_deleted, delay=delay, retries=retries, error=error
        )
