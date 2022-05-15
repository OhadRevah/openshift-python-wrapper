import pytest

from tests.network.service_mesh.utils import (
    assert_authentication_request,
    assert_traffic_management_request,
    inbound_request,
)
from utilities.exceptions import CommandExecFailed


pytestmark = pytest.mark.usefixtures(
    "skip_if_service_mesh_ovn_and_jira_1097_not_closed",
)


class TestSMTrafficManagement:
    @pytest.mark.polarion("CNV-5782")
    def test_service_mesh_traffic_management(
        self,
        skip_if_service_mesh_not_installed,
        traffic_management_service_mesh_convergence,
        server_deployment_v1,
        vm_cirros_with_service_mesh_annotation,
        service_mesh_ingress_service_addr,
    ):
        assert_traffic_management_request(
            vm=vm_cirros_with_service_mesh_annotation,
            server=server_deployment_v1,
            destination=service_mesh_ingress_service_addr,
        )

    @pytest.mark.polarion("CNV-7304")
    def test_service_mesh_traffic_management_manipulated_rule(
        self,
        skip_if_service_mesh_not_installed,
        traffic_management_service_mesh_convergence,
        change_routing_to_v2,
        server_deployment_v2,
        vm_cirros_with_service_mesh_annotation,
        service_mesh_ingress_service_addr,
    ):
        assert_traffic_management_request(
            vm=vm_cirros_with_service_mesh_annotation,
            server=server_deployment_v2,
            destination=service_mesh_ingress_service_addr,
        )


class TestSMPeerAuthentication:
    @pytest.mark.polarion("CNV-5784")
    def test_authentication_policy_from_mesh(
        self,
        skip_if_service_mesh_not_installed,
        peer_authentication_service_mesh_deployment,
        vm_cirros_with_service_mesh_annotation,
        httpbin_service_service_mesh,
    ):
        assert_authentication_request(
            vm=vm_cirros_with_service_mesh_annotation,
            service=httpbin_service_service_mesh.app_name,
        )

    @pytest.mark.polarion("CNV-7305")
    def test_authentication_policy_outside_mesh(
        self,
        skip_if_service_mesh_not_installed,
        peer_authentication_service_mesh_deployment,
        httpbin_service_service_mesh,
        outside_mesh_vm_cirros_with_service_mesh_annotation,
    ):
        with pytest.raises(CommandExecFailed):
            assert_authentication_request(
                vm=outside_mesh_vm_cirros_with_service_mesh_annotation,
                service=httpbin_service_service_mesh.app_name,
            )

    @pytest.mark.polarion("CNV-7128")
    def test_service_mesh_inbound_traffic_blocked(
        self,
        skip_if_service_mesh_not_installed,
        peer_authentication_service_mesh_deployment,
        vm_cirros_with_service_mesh_annotation,
        outside_mesh_vm_cirros_with_service_mesh_annotation,
        vmi_http_server,
    ):
        destionation_service_spec = (
            vm_cirros_with_service_mesh_annotation.custom_service.instance.spec
        )
        with pytest.raises(CommandExecFailed):
            inbound_request(
                vm=outside_mesh_vm_cirros_with_service_mesh_annotation,
                destination_address=destionation_service_spec.clusterIPs[0],
                destination_port=destionation_service_spec.ports[0].port,
            )
