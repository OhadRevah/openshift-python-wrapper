import copy
import logging
import re

import pytest
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutSampler
from openshift.dynamic.exceptions import NotFoundError

from tests.network.nmstate.constants import PUBLIC_DNS_SERVER_IP
from utilities.constants import NMSTATE_HANDLER
from utilities.infra import BUG_STATUS_CLOSED, get_pod_by_name_prefix, name_prefix
from utilities.network import (
    EthernetNetworkConfigurationPolicy,
    LinuxBridgeNodeNetworkConfigurationPolicy,
)


DNS_CONF_FILE = "/etc/resolv.conf"
CAT_RESOLV_CONF_CMD = f"cat {DNS_CONF_FILE}"


LOGGER = logging.getLogger(__name__)
IP_LIST = [{"ip": "1.1.1.1", "prefix-length": 24}]
BRIDGE_NAME = "br1test"
NNCP_CONFIGURING_STATUS = (
    LinuxBridgeNodeNetworkConfigurationPolicy.Conditions.Reason.CONFIGURATION_PROGRESSING
)

pytestmark = pytest.mark.sno


class MoreThanTwoDNSError(Exception):
    pass


@pytest.fixture(scope="class")
def nmstate_linux_bridge_device_worker(
    nodes_available_nics, utility_pods, worker_node1
):
    nmstate_br_dev = LinuxBridgeNodeNetworkConfigurationPolicy(
        name=f"nmstate-{name_prefix(worker_node1.name)}",
        bridge_name=BRIDGE_NAME,
        node_selector=worker_node1.hostname,
        ports=[nodes_available_nics[worker_node1.name][-1]],
        worker_pods=utility_pods,
    )
    yield nmstate_br_dev

    nmstate_br_dev.clean_up()


@pytest.fixture()
def nmstate_pod_on_worker_1(admin_client, hco_namespace, worker_node1):
    for pod in get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=NMSTATE_HANDLER,
        namespace=hco_namespace.name,
        get_all=True,
    ):
        if pod.node.name == worker_node1.name:
            return pod
    raise NotFoundError(
        f"No {NMSTATE_HANDLER} Pod of worker node {worker_node1.name} found."
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
def dns_gathered_current_nameservers(worker_node1_pod_executor):
    dns_data = worker_node1_pod_executor.exec(command=CAT_RESOLV_CONF_CMD)
    dns_nameservers = re.findall(r"\d+\.\d+\.\d+\.\d+", str(dns_data))
    LOGGER.info(f"{DNS_CONF_FILE} currently holds: {dns_nameservers}")
    return dns_nameservers


@pytest.fixture()
def dns_new_resolver(
    utility_pods,
    worker_node1,
    worker_node1_pod_executor,
    dns_gathered_current_nameservers,
):
    """
    This fixture uses the current DNS configurations of the node and creates the new dns_resolver configurations in
    order to configure the DNS.

    dns_resolve should not contain duplicate entries.

    Returns:
        dns_resolver (dict): new dns setting to configure in the NNCP
    """
    dns_resolver = {
        "config": {
            "server": [dns_gathered_current_nameservers[1], PUBLIC_DNS_SERVER_IP],
        }
    }

    return dns_resolver


@pytest.fixture()
def worker1_saved_original_interface_configurations(worker_node1, nodes_occupied_nics):
    nns = NodeNetworkState(name=worker_node1.name)
    return nns.get_interface(name=(nodes_occupied_nics[worker_node1.name][0]))


@pytest.fixture()
def generated_common_nncp(
    nodes_occupied_nics,
    worker_node1,
    utility_pods,
    worker1_saved_original_interface_configurations,
):
    node_nics = nodes_occupied_nics[worker_node1.name]
    ipv4_data = worker1_saved_original_interface_configurations["ipv4"]
    common_nncp_dict = {
        "node_selector": worker_node1.hostname,
        "ipv4_dhcp": ipv4_data["dhcp"],
        "ipv4_enable": ipv4_data["enabled"],
        "ipv4_auto_dns": ipv4_data["auto-dns"],
        "worker_pods": utility_pods,
        "interfaces_name": node_nics,
        "node_active_nics": node_nics,
    }
    return common_nncp_dict


@pytest.fixture()
def dns_nncp(
    worker_node1,
    utility_pods,
    nodes_occupied_nics,
    generated_common_nncp,
):
    LOGGER.info(f"Current node IPv4 configurations: {generated_common_nncp}")
    with EthernetNetworkConfigurationPolicy(
        name=f"dns-{name_prefix(worker_node1.name)}",
        **generated_common_nncp,
    ) as nncp_dns:
        nncp_dns.wait_for_status_success()
        yield nncp_dns


@pytest.fixture()
def dns_nncp_restored(
    worker_node1,
    utility_pods,
    nodes_occupied_nics,
    generated_common_nncp,
):
    yield
    LOGGER.info("Restoring DNS configurations on the node")
    with EthernetNetworkConfigurationPolicy(
        name=f"dns-{name_prefix(worker_node1.name)}-restored",
        dns_resolver={"config": {"server": []}},
        **generated_common_nncp,
    ) as nncp_dns:
        nncp_dns.wait_for_status_success()


@pytest.fixture()
def dns_nncp_configured(
    worker_node1,
    dns_new_resolver,
    utility_pods,
    dns_nncp,
    worker1_saved_original_interface_configurations,
):
    LOGGER.info("Editing the existing NNCP with the new DNS configuration")
    interfaces_dict = copy.deepcopy(
        dict(worker1_saved_original_interface_configurations)
    )
    interfaces_dict["ipv4"]["auto-dns"] = False
    with ResourceEditor(
        patches={
            dns_nncp: {
                "spec": {
                    "desiredState": {
                        "dns-resolver": dns_new_resolver,
                        "interfaces": [interfaces_dict],
                    },
                }
            }
        }
    ):
        dns_nncp.wait_for_status_success()
        yield dns_nncp


@pytest.fixture()
def assured_two_or_less_dns_nameservers(request, dns_gathered_current_nameservers):
    dns_num_nameserver = len(dns_gathered_current_nameservers)
    max_allowed_dns_nameservers = 2
    if dns_num_nameserver > max_allowed_dns_nameservers:
        LOGGER.error(
            f"{DNS_CONF_FILE} has {dns_num_nameserver} nameservers configured (more than "
            f"{max_allowed_dns_nameservers}!). {request.node.name} can only run on clusters that are configured with "
            f"{max_allowed_dns_nameservers} or less "
            "DNS nameservers"
        )
        raise MoreThanTwoDNSError


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
        node_selector=worker_node1.hostname,
        ipv4_dhcp=False,
        worker_pods=utility_pods,
        interfaces_name=[nodes_available_nics[worker_node1.name][-1]],
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
        node_selector=worker_node1.hostname,
        ipv4_dhcp=False,
        ipv4_enable=True,
        ipv4_addresses=IP_LIST,
        worker_pods=utility_pods,
        interfaces_name=[nodes_available_nics[worker_node1.name][-1]],
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
        node_selector=worker_node1.hostname,
        ipv4_dhcp=True,
        ipv4_enable=True,
        worker_pods=utility_pods,
        interfaces_name=[nodes_available_nics[worker_node1.name][-1]],
        node_active_nics=nodes_occupied_nics[worker_node1.name],
    ):
        LOGGER.info("NMstate: Test with dynamic IP")


@pytest.mark.xfail(
    raises=MoreThanTwoDNSError,
)
@pytest.mark.bugzilla(
    2007459, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-5724")
def test_dns(
    assured_two_or_less_dns_nameservers,
    worker_node1,
    utility_pods,
    dns_new_resolver,
    worker_node1_pod_executor,
    dns_nncp_configured,
    dns_nncp_restored,
):
    LOGGER.info("NMstate: Test DNS")

    dns_current_state = worker_node1_pod_executor.exec(command=CAT_RESOLV_CONF_CMD)
    dns_redhat_nameserver = dns_new_resolver["config"]["server"][0]
    err_msg = "NNCP failed to configure the dns address {dns_server_ips} on the node's interface"
    assert dns_redhat_nameserver in dns_current_state, err_msg.format(
        dns_server_ips=dns_redhat_nameserver
    )
    assert PUBLIC_DNS_SERVER_IP in dns_current_state, err_msg.format(
        dns_server_ips=PUBLIC_DNS_SERVER_IP
    )


@pytest.mark.polarion("CNV-5725")
def test_static_route(
    skip_if_no_multinic_nodes,
    worker_node1,
    utility_pods,
    nodes_occupied_nics,
    nodes_available_nics,
):
    iface_name = nodes_available_nics[worker_node1.name][-1]
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
        node_selector=worker_node1.hostname,
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
