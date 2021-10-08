import pytest

from tests.network.service_mesh.utils import assert_traffic_management_request


class TestSMTrafficManagement:
    @pytest.mark.order(before="test_service_mesh_traffic_management_manipulated_rule")
    @pytest.mark.polarion("CNV-5782")
    def test_service_mesh_traffic_management(
        self,
        traffic_management_sm_convergence,
        server_deployment_v1,
        vm_cirros_with_sm_annotation,
        sm_ingress_service_addr,
    ):
        assert_traffic_management_request(
            vm=vm_cirros_with_sm_annotation,
            server=server_deployment_v1,
            destination=sm_ingress_service_addr,
        )

    @pytest.mark.polarion("CNV-7304")
    def test_service_mesh_traffic_management_manipulated_rule(
        self,
        traffic_management_sm_convergence,
        change_routing_to_v2,
        server_deployment_v2,
        vm_cirros_with_sm_annotation,
        sm_ingress_service_addr,
    ):
        assert_traffic_management_request(
            vm=vm_cirros_with_sm_annotation,
            server=server_deployment_v2,
            destination=sm_ingress_service_addr,
        )
