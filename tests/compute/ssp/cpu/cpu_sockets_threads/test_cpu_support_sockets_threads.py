"""
Test cpu support for sockets and threads
"""

import time
import pytest
import xmltodict
from openshift.dynamic.exceptions import UnprocessibleEntityError
from tests import utils as test_utils
from tests.utils import VirtualMachineForTests
from resources.namespace import Namespace


def check_vm_dumpxml(vm, cores, sockets, threads):
    def _parse_xml(vm):
        test_utils.wait_for_vm_interfaces(vm.vmi)
        data_xml = vm.vmi.get_xml()
        xml_dict = xmltodict.parse(data_xml, process_namespaces=True)
        return xml_dict["domain"]["cpu"]["topology"]

    cpu = _parse_xml(vm)
    if sockets:
        assert cpu["@sockets"] == str(
            sockets
        ), f"CPU sockets: Expected {sockets}, Found: {cpu['@sockets']}"
    if cores:
        assert cpu["@cores"] == str(
            cores
        ), f"CPU cores: Expected {cores}, Found: {cpu['@cores']}"
    if threads:
        assert cpu["@threads"] == str(
            threads
        ), f"CPU threads: Expected {threads}, Found: {cpu['@threads']}"


@pytest.fixture(scope="module", autouse=True)
def cpu_sockets_threads_ns():
    with Namespace(name="cpu-sockets-threads-ns") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns


@pytest.fixture(
    params=[
        pytest.param(
            {"sockets": 2, "cores": 2, "threads": 2},
            marks=(pytest.mark.polarion("CNV-2820")),
            id="case1: 2 cores, 2 threads, 2 sockets",
        ),
        pytest.param(
            {"sockets": None, "cores": 1, "threads": 2},
            marks=(pytest.mark.polarion("CNV-2823")),
            id="case2: 1 cores, 2 threads, no sockets",
        ),
        pytest.param(
            {"sockets": 2, "cores": 1, "threads": None},
            marks=(pytest.mark.polarion("CNV-2822")),
            id="case3: 1 cores, no threads, 2 sockets",
        ),
        pytest.param(
            {"sockets": None, "cores": 2, "threads": None},
            marks=(pytest.mark.polarion("CNV-2821")),
            id="case4: 2 cores, no threads, no sockets",
        ),
    ]
)
def vm_with_cpu_support(request, cpu_sockets_threads_ns):
    """
    VM with CPU support (cores,sockets,threads)
    """

    with test_utils.VirtualMachineForTests(
        name=f"vm-cpu-support-{time.time()}",
        namespace=cpu_sockets_threads_ns.name,
        cpu_cores=request.param["cores"],
        cpu_sockets=request.param["sockets"],
        cpu_threads=request.param["threads"],
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def no_cpu_settings_vm(cpu_sockets_threads_ns):
    """
    Create VM without specific CPU settings
    """
    with VirtualMachineForTests(
        name="no-cpu-settings-vm", namespace=cpu_sockets_threads_ns.name
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.mark.polarion("CNV-1485")
def test_vm_with_no_cpu_settings(no_cpu_settings_vm):
    """
    Test VM without cpu setting, check XML:
        <topology sockets='1' cores='1' threads='1'/>
    """
    check_vm_dumpxml(vm=no_cpu_settings_vm, sockets="1", cores="1", threads="1")


@pytest.mark.polarion("CNV-2818")
def test_vm_with_cpu_limitation(cpu_sockets_threads_ns):
    """
    Test VM with cpu limitation, CPU requests and limits are equals
    """
    with test_utils.VirtualMachineForTests(
        name="vm-cpu-limitation",
        namespace=cpu_sockets_threads_ns.name,
        cpu_cores=2,
        cpu_limits=2,
        cpu_requests=2,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        check_vm_dumpxml(vm=vm, sockets="1", cores="2", threads="1")


@pytest.mark.polarion("CNV-2819")
def test_vm_with_cpu_limitation_negative(cpu_sockets_threads_ns):
    """
    Test VM with cpu limitation
    negative case: CPU requests is larger then limits
    """
    with pytest.raises(UnprocessibleEntityError):
        with test_utils.VirtualMachineForTests(
            name="vm-cpu-limitation-negative",
            namespace=cpu_sockets_threads_ns.name,
            cpu_limits=2,
            cpu_requests=4,
        ):
            pass


def test_vm_with_cpu_support(vm_with_cpu_support):
    """
    Test VM with cpu support
    """
    check_vm_dumpxml(
        vm=vm_with_cpu_support,
        sockets=vm_with_cpu_support.cpu_sockets,
        cores=vm_with_cpu_support.cpu_cores,
        threads=vm_with_cpu_support.cpu_threads,
    )
