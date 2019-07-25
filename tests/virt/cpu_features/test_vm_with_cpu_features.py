"""
VM with CPU features
"""
import pytest
from tests import utils as test_utils
from utilities import console
from resources.resource import WaitForStatusTimedOut


@pytest.fixture(
    params=[
        pytest.param(
            [{"features": [{"name": "pcid"}]}, "no-policy"],
            marks=(pytest.mark.polarion("CNV-1830")),
        ),
        pytest.param(
            [{"features": [{"name": "pcid", "policy": "force"}]}, "policy-force"],
            marks=(pytest.mark.polarion("CNV-1836")),
        ),
    ],
    ids=["Feature: name: pcid", "Feature: name: pcid , policy:force"],
)
def cpu_features_vm_positive(request, default_client, cpu_features_namespace):
    with test_utils.FedoraVirtualMachine(
        name=f"vm-cpu-features-positive-{request.param[1]}",
        namespace=cpu_features_namespace.name,
        cpu_flags=request.param[0],
    ) as vm:
        vm.start(wait=True, timeout=240)
        test_utils.wait_for_vm_interfaces(vm.vmi)
        yield vm


@pytest.fixture(
    params=[
        pytest.param(
            [{"features": [{"name": "nomatch"}]}, "nomatch"],
            marks=(pytest.mark.polarion("CNV-1833")),
        ),
        pytest.param(
            [{"features": [{"name": "pcid", "policy": "forbid"}]}, "policy-forbid"],
            marks=(pytest.mark.polarion("CNV-1835")),
        ),
    ],
    ids=["Feature: name: nomatch", "Feature: name: pcid , policy:forbid "],
)
def cpu_features_vm_negative(request, default_client, cpu_features_namespace):
    with test_utils.FedoraVirtualMachine(
        name=f"vm-cpu-features-negative-{request.param[1]}",
        namespace=cpu_features_namespace.name,
        cpu_flags=request.param[0],
    ) as vm:
        vm.start()
        yield vm


def test_vm_with_cpu_feature_positive(cpu_features_vm_positive):
    """
    Test VM with cpu flag, test the VM started and enter the console
    """
    assert cpu_features_vm_positive.cpu_flags["features"][0]["name"] == (
        cpu_features_vm_positive.instance["spec"]["template"]["spec"]["domain"]["cpu"][
            "features"
        ][0]["name"]
    )
    with console.Fedora(vm=cpu_features_vm_positive) as vm_console:
        vm_console.sendline("cat /etc/redhat-release | wc -l\n")
        vm_console.expect("1", timeout=20)


def test_vm_with_cpu_feature_negative(cpu_features_vm_negative):
    """
    Negative test:
    Test VM with wrong/unsupported cpu feature policy,
    VM should not run in this case.
    """
    with pytest.raises(WaitForStatusTimedOut):
        cpu_features_vm_negative.vmi.wait_until_running(timeout=60)
