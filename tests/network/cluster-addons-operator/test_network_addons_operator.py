import logging

import pytest

LOGGER = logging.getLogger(__name__)


@pytest.mark.polarion("CNV-2520")
def test_component_installed_by_operator(network_addons_config_cr):
    """
    Verify that the network addons operator is supposed to install Linux-Bridge
    (a mandatory default component), by checking if the component appears in
    the operator CR.
    """
    component_name_in_cr = "linuxBridge"
    assert (
        component_name_in_cr in network_addons_config_cr.instance.spec.keys()
    ), f"{component_name_in_cr} is missing from the network operator CR."


@pytest.mark.polarion("CNV-2296")
def test_linux_bridge_functionality(bridge_attached_vm):
    """
    Verify the linux-bridge component valid functionality.
    Start a VM and verify it starts successfully, as an indication of successful
    deployment of linux-bridge.
    """
    assert bridge_attached_vm.vmi.wait_until_running()
