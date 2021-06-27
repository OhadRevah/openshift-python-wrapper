import logging

import pytest
from ocp_resources.utils import TimeoutSampler
from openshift.dynamic.exceptions import NotFoundError

from utilities.infra import BUG_STATUS_CLOSED, get_pod_by_name_prefix, name_prefix
from utilities.network import (
    EthernetNetworkConfigurationPolicy,
    LinuxBridgeNodeNetworkConfigurationPolicy,
)


LOGGER = logging.getLogger(__name__)
IP_LIST = [{"ip": "1.1.1.1", "prefix-length": 24}]
BRIDGE_NAME = "br1test"
NNCP_CONFIGURING_STATUS = (
    LinuxBridgeNodeNetworkConfigurationPolicy.Conditions.Reason.CONFIGURING
)

pytestmark = pytest.mark.sno


@pytest.fixture(scope="class")
def nmstate_linux_bridge_device_worker(
    nodes_available_nics, utility_pods, worker_node1
):
    nmstate_br_dev = LinuxBridgeNodeNetworkConfigurationPolicy(
        name=f"nmstate-{name_prefix(worker_node1.name)}",
        bridge_name=BRIDGE_NAME,
        node_selector=worker_node1.name,
        ports=[nodes_available_nics[worker_node1.name][0]],
        worker_pods=utility_pods,
    )
    yield nmstate_br_dev

    nmstate_br_dev.clean_up()


@pytest.fixture()
def nmstate_pod_on_worker_1(admin_client, hco_namespace, worker_node1):
    for pod in get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix="nmstate-handler",
        namespace=hco_namespace.name,
        get_all=True,
    ):
        if pod.node.name == worker_node1.name:
            return pod
    raise NotFoundError(
        f"No nmstate-handler Pod of worker node {worker_node1.name} found."
    )


@pytest.fixture()
def deleted_nmstate_pod_during_nncp_configuration(
    nmstate_ds, nmstate_linux_bridge_device_worker, nmstate_pod_on_worker_1
):
    # Bridge device created here as we need to catch it once in 'ConfigurationProgressing' status.
    nmstate_linux_bridge_device_worker.create()

    sampler = TimeoutSampler(
        wait_timeout=15,
        sleep=1,
        func=lambda: nmstate_linux_bridge_device_worker.status()
        == NNCP_CONFIGURING_STATUS,
    )
    for sample in sampler:
        if sample:
            # Configuration in progress
            nmstate_pod_on_worker_1.delete(wait=True)
            nmstate_ds.wait_until_deployed()
            return


@pytest.mark.polarion("CNV-5721")
def test_no_ip(
    skip_if_no_multinic_nodes,
    worker_node1,
    utility_pods,
    nodes_occupied_nics,
    nodes_available_nics,
):
    with EthernetNetworkConfigurationPolicy(
        name=f"no-ip-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        ipv4_dhcp=False,
        worker_pods=utility_pods,
        interfaces_name=[nodes_available_nics[worker_node1.name][0]],
        node_active_nics=nodes_occupied_nics[worker_node1.name],
    ):
        LOGGER.info("NNCP: Test no IP")


@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-5720")
def test_static_ip(
    skip_if_no_multinic_nodes,
    worker_node1,
    utility_pods,
    nodes_occupied_nics,
    nodes_available_nics,
):
    with EthernetNetworkConfigurationPolicy(
        name=f"static-ip-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        ipv4_dhcp=False,
        ipv4_enable=True,
        ipv4_addresses=IP_LIST,
        worker_pods=utility_pods,
        interfaces_name=[nodes_available_nics[worker_node1.name][0]],
        node_active_nics=nodes_occupied_nics[worker_node1.name],
    ):
        LOGGER.info("NMstate: Test with IP")


@pytest.mark.polarion("CNV-5722")
def test_dynamic_ip(
    skip_if_no_multinic_nodes,
    worker_node1,
    utility_pods,
    nodes_occupied_nics,
    nodes_available_nics,
):
    with EthernetNetworkConfigurationPolicy(
        name=f"dynamic-ip-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        ipv4_dhcp=True,
        ipv4_enable=True,
        worker_pods=utility_pods,
        interfaces_name=[nodes_available_nics[worker_node1.name][0]],
        node_active_nics=nodes_occupied_nics[worker_node1.name],
    ):
        LOGGER.info("NMstate: Test with dynamic IP")


@pytest.mark.bugzilla(
    1926143, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-5724")
def test_dns(worker_node1, utility_pods, nodes_occupied_nics):
    dns_resolver = {
        "config": {
            "search": ["example.com"],
            "server": ["8.8.8.8"],
        }
    }
    with EthernetNetworkConfigurationPolicy(
        name=f"dns-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        dns_resolver=dns_resolver,
    ):
        LOGGER.info("NMstate: Test DNS")


@pytest.mark.polarion("CNV-5725")
def test_static_route(
    skip_if_no_multinic_nodes,
    worker_node1,
    utility_pods,
    nodes_occupied_nics,
    nodes_available_nics,
):
    iface_name = nodes_available_nics[worker_node1.name][0]
    routes = {
        "config": [
            {
                "destination": "2.2.2.0/24",
                "metric": 150,
                "next-hop-address": "1.1.1.254",
                "next-hop-interface": iface_name,
            }
        ]
    }
    with EthernetNetworkConfigurationPolicy(
        name=f"static-route-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        ipv4_dhcp=False,
        ipv4_enable=True,
        ipv4_addresses=IP_LIST,
        worker_pods=utility_pods,
        interfaces_name=[iface_name],
        node_active_nics=nodes_occupied_nics[worker_node1.name],
        routes=routes,
    ):
        LOGGER.info("NMstate: Test static route")


class TestNmstatePodDeletion:
    @pytest.mark.polarion("CNV-6559")
    def test_delete_nmstate_pod_during_nncp_configuration(
        self,
        nmstate_linux_bridge_device_worker,
        deleted_nmstate_pod_during_nncp_configuration,
    ):
        """
        Delete nmstate-handler pod while NNCP is on status 'ConfigurationProgressing'.
        Test that NNCP is NOT on status 'ConfigurationProgressing' and loop breaks.
        """
        assert nmstate_linux_bridge_device_worker.status() != NNCP_CONFIGURING_STATUS, (
            f"{nmstate_linux_bridge_device_worker.name} is still on status "
            f"{NNCP_CONFIGURING_STATUS} after nmstate pod has been deleted."
        )

    @pytest.mark.order(after="test_delete_nmstate_pod_during_nncp_configuration")
    @pytest.mark.polarion("CNV-6743")
    def test_nncp_configured_successfully_after_pod_deletion(
        self,
        nmstate_linux_bridge_device_worker,
    ):
        """
        Test that NNCP has been configured Successfully. (The nmstate-handler pod released the lock).
        """
        nmstate_linux_bridge_device_worker.wait_for_status_success()
