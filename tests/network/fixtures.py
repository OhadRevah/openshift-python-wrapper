# -*- coding: utf-8 -*-

"""
Pytest fixtures file for CNV network tests
"""
import logging

import pytest

from resources.virtual_machine_instance import VirtualMachineInstance
from tests import utils as test_utils

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope='class')
def update_vms_pod_ip_info(request):
    """
    Find VM Pod IP and update the VMs dict
    """
    vms = test_utils.get_fixture_val(request=request, attr_name="vms")
    namespace = test_utils.get_fixture_val(request=request, attr_name="namespace")
    for vmi in vms:
        vmi_object = VirtualMachineInstance(name=vmi, namespace=namespace)
        vmi_data = vmi_object.get()
        ifcs = vmi_data.get('status', {}).get('interfaces', [])
        active_ifcs = [i.get('ipAddress') for i in ifcs if i.get('interfaceName') == "eth0"]
        vms[vmi]["interfaces"]["pod"] = [active_ifcs[0].split("/")[0]]
