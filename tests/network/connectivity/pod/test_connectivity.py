"""
VM to VM connectivity
"""

import pytest
from pytest_testconfig import config as py_config

from tests.fixtures import (
    create_vms_from_template,
    wait_until_vmis_running,
    wait_for_vmis_interfaces_report,
    start_vms,
)
from tests.network.connectivity import utils
from tests.network.fixtures import update_vms_pod_ip_info
from tests.network.connectivity import config


@pytest.mark.usefixtures(
    create_vms_from_template.__name__,
    start_vms.__name__,
    wait_until_vmis_running.__name__,
    wait_for_vmis_interfaces_report.__name__,
    update_vms_pod_ip_info.__name__,
)
class TestConnectivityPodNetwork(object):
    """
    Test VM to VM connectivity
    """
    vms = {
        "vm-fedora-1": {
            "cloud_init": config.CLOUD_INIT,
        },
        "vm-fedora-2": {
            "cloud_init": config.CLOUD_INIT,
        }
    }
    namespace = config.NETWORK_NS
    template = config.VM_YAML_FEDORA
    template_kwargs = config.VM_FEDORA_ATTRS
    src_vm = list(vms.keys())[0]
    dst_vm = list(vms.keys())[1]

    @pytest.mark.polarion("CNV-2332")
    def test_connectivity_over_pod_network(self):
        """
        Check connectivity
        """
        dst_ip = self.vms[self.dst_vm]["interfaces"]["pod"][0]
        utils.run_test_connectivity(
            src_vm=self.src_vm, dst_vm=self.dst_vm, dst_ip=dst_ip, positive=True
        )

    @pytest.mark.polarion("CNV-2334")
    def test_guest_performance_over_pod_network(self, is_bare_metal):
        """
        In-guest performance bandwidth passthrough over Linux bridge
        """
        if not is_bare_metal:
            pytest.skip(msg='Only run on bare metal env')

        expected_res = py_config['test_guest_performance']['bandwidth']
        listen_ip = self.src_vm["interfaces"]['pod'][0]
        bits_per_second = utils.run_test_guest_performance(
            server_vm=self.src_vm, client_vm=self.src_vm, listen_ip=listen_ip
        )
        assert bits_per_second >= expected_res
