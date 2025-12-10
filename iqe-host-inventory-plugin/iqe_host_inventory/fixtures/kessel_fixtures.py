# mypy: disallow-untyped-defs

from collections.abc import Generator

import pytest
from iqe.base.application import Application
from iqe.base.http import RobustSession
from iqe_turnpike.tests.config_wrappers import get_primary_turnpike_user
from kessel.relations.v1beta1.relation_tuples_pb2_grpc import KesselTupleServiceStub

from iqe_host_inventory.modeling.kessel_relations import HBIKesselRelationsGRPC


@pytest.fixture(scope="session")
def hbi_turnpike_http_client(
    application: Application,
) -> Generator[RobustSession | None, None, None]:
    if application.config.current_env.lower() in ("clowder_smoke", "ephemeral", "smoke"):
        yield None
        return

    with application.copy_using(
        user=get_primary_turnpike_user(application), auth_type="cert"
    ) as app:
        yield app.http_client


@pytest.fixture(scope="session")
def hbi_kessel_relations_grpc(
    application: Application,
    relations_tuples_grpc: KesselTupleServiceStub,
    hbi_turnpike_http_client: RobustSession | None,
) -> HBIKesselRelationsGRPC:
    return HBIKesselRelationsGRPC(
        env=application.config.current_env,
        grpc_service=relations_tuples_grpc,
        turnpike_http_client=hbi_turnpike_http_client,
    )
