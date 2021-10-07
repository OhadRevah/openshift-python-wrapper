import copy
import logging
import re

import pytest
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutSampler
from openshift.dynamic.exceptions import NotFoundError

from tests.network.nmstate.constants import PUBLIC_DNS_SERVER_IP
from utilities.infra import (
    BUG_STATUS_CLOSED,
    ExecCommandOnPod,
    get_pod_by_name_prefix,
    name_prefix,
)
from utilities.network import (
    EthernetNetworkConfigurationPolicy,
    LinuxBridgeNodeNetworkConfigurationPolicy,
)


CAT_RESOLV_CONF_CMD = "cat /etc/resolv.conf"


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


@pytest.fixture()
def pod_executor(utility_pods, worker_node1):
    return ExecCommandOnPod(utility_pods=utility_pods, node=worker_node1)


@pytest.fixture()
def dns_gathered_current_state(utility_pods, worker_node1, pod_executor):
    """
    This fixture gathers the current DNS configurations from the node and creates the new dns_resolver configurations in
    order to configure the DNS.

    dns_resolve should not contain duplicate entries.

    Returns:
        dns_resolver (dict): new dns setting to configure in the NNCP
    """
    dns_data = pod_executor.exec(command=CAT_RESOLV_CONF_CMD)
    dns_addresses = re.findall(r"\d+\.\d+\.\d+\.\d", str(dns_data))
    LOGGER.info(f"resolv.conf currently holds: {dns_addresses}")
    dns_resolver = {
        "config": {
            "server": [dns_addresses[1], PUBLIC_DNS_SERVER_IP],
        }
    }

    return dns_resolver


@pytest.fixture()
def worker1_saved_original_interface_configurations(worker_node1, nodes_occupied_nics):
    nns = NodeNetworkState(name=worker_node1.name)
    return nns.get_interface(name=(nodes_occupied_nics[worker_node1.name][0]))


@pytest.fixture()
def dns_nncp(
    worker_node1,
    utility_pods,
    nodes_occupied_nics,
    worker1_saved_original_interface_configurations,
):
    node_nics = nodes_occupied_nics[worker_node1.name]
    with EthernetNetworkConfigurationPolicy(
        name=f"dns-{name_prefix(worker_node1.name)}",
        node_selector=worker_node1.name,
        ipv4_dhcp=worker1_saved_original_interface_configurations.ipv4["dhcp"],
        ipv4_enable=worker1_saved_original_interface_configurations.ipv4["enabled"],
        ipv4_auto_dns=worker1_saved_original_interface_configurations.ipv4["auto-dns"],
        worker_pods=utility_pods,
        interfaces_name=node_nics,
        node_active_nics=node_nics,
    ) as nncp_dns:
        nncp_dns.wait_for_status_success()
        yield nncp_dns


@pytest.fixture()
def dns_nncp_restored(
    worker_node1,
    utility_pods,
    nodes_occupied_nics,
    worker1_saved_original_interface_configurations,
):
    yield
    LOGGER.info("Restoring DNS configurations on the node")
    node_nics = nodes_occupied_nics[worker_node1.name]
    with EthernetNetworkConfigurationPolicy(
        name=f"dns-{name_prefix(worker_node1.name)}-restored",
        node_selector=worker_node1.name,
        ipv4_dhcp=worker1_saved_original_interface_configurations.ipv4["dhcp"],
        ipv4_enable=worker1_saved_original_interface_configurations.ipv4["enabled"],
        ipv4_auto_dns=worker1_saved_original_interface_configurations.ipv4["auto-dns"],
        worker_pods=utility_pods,
        interfaces_name=node_nics,
        node_active_nics=node_nics,
        dns_resolver={"config": {"server": []}},
    ) as nncp_dns:
        nncp_dns.wait_for_status_success()


@pytest.fixture()
def dns_nncp_configured(
    worker_node1,
    dns_gathered_current_state,
    utility_pods,
    dns_nncp,
    worker1_saved_original_interface_configurations,
):
    LOGGER.info("Editing the existing NNCP with the new DNS configuration")
    interfaces_dict = copy.copy(dict(worker1_saved_original_interface_configurations))
    # ipv4 is ResourceField and needs to be converted to dict.
    interfaces_dict["ipv4"] = dict(interfaces_dict["ipv4"])
    interfaces_dict["ipv4"]["auto-dns"] = False
    with ResourceEditor(
        patches={
            dns_nncp: {
                "spec": {
                    "desiredState": {
                        "dns-resolver": dns_gathered_current_state,
                        "interfaces": [interfaces_dict],
                    },
                }
            }
        }
    ):
        dns_nncp.wait_for_status_success()
        yield dns_nncp


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
def test_dns(
    worker_node1,
    utility_pods,
    pod_executor,
    dns_gathered_current_state,
    dns_nncp_configured,
    dns_nncp_restored,
):
    LOGGER.info("NMstate: Test DNS")
    dns_current_state = pod_executor.exec(command=CAT_RESOLV_CONF_CMD)
    assert (
        PUBLIC_DNS_SERVER_IP in dns_current_state
        and dns_gathered_current_state["config"]["server"][0] in dns_current_state
    ), f"NNCP failed to configure the new dns address, {PUBLIC_DNS_SERVER_IP}, on the node's interface"


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

    @pytest.mark.bugzilla(
        2000052, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
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
