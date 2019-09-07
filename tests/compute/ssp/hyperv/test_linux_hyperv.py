# -*- coding: utf-8 -*-

"""
[SSP] hyperv feature - checking VMI XML
This test case includes only Linux based test case
"""

import xmltodict
import pytest
from tests.utils import TestVirtualMachine
from resources.namespace import Namespace


class HyperVVM(TestVirtualMachine):
    def __init__(self, name, namespace):
        super().__init__(
            name=name, namespace=namespace, label="HyperV", cpu_cores=1, memory="1G"
        )

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"]["template"]["spec"]["domain"]["clock"] = {
            "utc": {},
            "timer": {
                "hpet": {"present": False},
                "pit": {"tickPolicy": "delay"},
                "rtc": {"tickPolicy": "catchup"},
                "hyperv": {},
            },
        }
        res["spec"]["template"]["spec"]["domain"]["features"] = {
            "acpi": {},
            "apic": {},
            "hyperv": {
                "relaxed": {},
                "vapic": {},
                "synictimer": {},
                "vpindex": {},
                "synic": {},
                "spinlocks": {"spinlocks": 8191},
            },
        }
        return res


@pytest.fixture(scope="session", autouse=True)
def ssp_linuxhyperv_namespace():
    with Namespace(name="cnv-ssp-linuxhyperv-ns") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns


@pytest.mark.polarion("CNV-2651")
def test_linux_hyperv(ssp_linuxhyperv_namespace):
    """
    Linux test: check hyperV with VM dumpxml
    """
    with HyperVVM(name="hyperv-test", namespace=ssp_linuxhyperv_namespace.name) as vm:
        vm.start(wait=True)
        vmi = vm.vmi
        vmi.wait_until_running()
        dataxml = vmi.get_xml()
        xml_dict = xmltodict.parse(dataxml, process_namespaces=True)
        features = xml_dict["domain"]["features"]
        hyperv = features["hyperv"]
        assert hyperv["relaxed"]["@state"] == "on"
        assert hyperv["vapic"]["@state"] == "on"
        assert hyperv["spinlocks"]["@state"] == "on"
        assert hyperv["spinlocks"]["@retries"] == "8191"
