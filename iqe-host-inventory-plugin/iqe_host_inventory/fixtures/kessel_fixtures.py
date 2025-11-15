# mypy: disallow-untyped-defs

import pytest
from kessel.relations.v1beta1.relation_tuples_pb2_grpc import KesselTupleServiceStub

from iqe_host_inventory.modeling.kessel_relations import HBIKesselRelationsGRPC


@pytest.fixture(scope="session")
def hbi_kessel_relations_grpc(
    relations_tuples_grpc: KesselTupleServiceStub,
) -> HBIKesselRelationsGRPC:
    return HBIKesselRelationsGRPC(relations_tuples_grpc)
