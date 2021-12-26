import logging
import re
from copy import deepcopy

import pytest
from ocp_resources.sriov_network_node_policy import SriovNetworkNodePolicy
from ocp_resources.storage_class import StorageClass
from ocp_resources.template import Template

from tests.compute.contants import DISK_SERIAL, RHSM_SECRET_NAME
from tests.compute.ssp.constants import VIRTIO
from tests.compute.utils import generate_rhsm_cloud_init_data, generate_rhsm_secret
from utilities import console
from utilities.constants import SRIOV
from utilities.infra import (
    BUG_STATUS_CLOSED,
    ExecCommandOnPod,
    get_bug_status,
    run_ssh_commands,
)
from utilities.network import network_nad
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    get_template_by_labels,
    running_vm,
    wait_for_console,
)


LOGGER = logging.getLogger(__name__)
SAP_HANA_VM_TEST_NAME = "TestSAPHANAVirtualMachine::test_sap_hana_running_vm"
SAP_HANA_VM_NAME = "sap-hana-vm"
INVTSC = "invtsc"
CPU_TIMER_LABEL_PREFIX = "cpu-timer.node.kubevirt.io"
LSCPU_CMD = "lscpu"
REQUIRED_NUMBER_OF_NETWORKS = 3
HANA_NODE_ROLE = "node-role.kubernetes.io/sap"


class SAPHANAVirtaulMachine(VirtualMachineForTestsFromTemplate):
    volume_name = "rhsm-secret-vol"

    def __init__(
        self,
        name,
        namespace,
        client,
        labels,
        node_selector,
        cloud_init_data,
        data_volume_template,
        sriov_nads,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            labels=labels,
            node_selector=node_selector,
            cloud_init_data=cloud_init_data,
            data_volume_template=data_volume_template,
            attached_secret={
                "volume_name": SAPHANAVirtaulMachine.volume_name,
                "serial": DISK_SERIAL,
                "secret_name": RHSM_SECRET_NAME,
            },
        )
        self.sriov_nads = sriov_nads

    def to_dict(self):
        res = super().to_dict()
        spec_template = res["spec"]["template"]["spec"]
        disks = spec_template["domain"]["devices"]["disks"]
        secret_disk = [
            disk for disk in disks if disk["name"] == SAPHANAVirtaulMachine.volume_name
        ][0]
        secret_disk["disk"]["bus"] = VIRTIO

        # TODO: Provide SRIOV_NETWORK_NAME parameters once bug is closed
        if get_bug_status(bug=2039683) not in BUG_STATUS_CLOSED:
            networks = spec_template["networks"]
            multus_networks = [
                network["multus"] for network in networks if network.get("multus")
            ]
            for network_index, multus_network in enumerate(multus_networks):
                multus_network[
                    "networkName"
                ] = f"{self.namespace}/{self.sriov_nads[network_index].name}"

        return res


def get_node_labels_by_name_subset(node, label_name_subset):
    return {
        label_name: label_value
        for label_name, label_value in node.labels.items()
        if label_name_subset in label_name
    }


def assert_node_label_exists(node, label_name):
    assert label_name, f"Node {node.name} does not have {label_name} label."


def get_parameters_from_template(template, parameter_subset):
    """Retruns a dict with matching template parameters.

    Args:
        template (Template): Template
        parameter_subset (str): Parameter name subset; may apply to a number of parameters

    Returns:
        dict: {parameter name: parameter value}
    """
    return {
        parameter["name"]: parameter["value"]
        for parameter in template.instance.parameters
        if parameter_subset in parameter["name"]
    }


def verify_vm_cpu_topology(vm, vmi_xml_dict, guest_cpu_config, template):
    LOGGER.info(f"Verify {vm.name} CPU configuration in libvirt and guest")
    vm_cpu_config = vmi_xml_dict["cpu"]["topology"]
    template_cpu_config = get_parameters_from_template(
        template=template, parameter_subset="CPU_"
    )

    failed_cpu_configuration = []
    if not (
        vm_cpu_config["@sockets"]
        == template_cpu_config["CPU_SOCKETS"]
        == guest_cpu_config["sockets"]
    ):
        failed_cpu_configuration.append("sockets")
    if not (
        vm_cpu_config["@cores"]
        == template_cpu_config["CPU_CORES"]
        == guest_cpu_config["cores"]
    ):
        failed_cpu_configuration.append("cores")
    if not (
        vm_cpu_config["@threads"]
        == template_cpu_config["CPU_THREADS"]
        == guest_cpu_config["threads"]
    ):
        failed_cpu_configuration.append("threads")

    assert not failed_cpu_configuration, (
        f"VM failed {failed_cpu_configuration} CPU topology configuration:\n expected: {template_cpu_config}\n "
        f"libvirt spec:{vm_cpu_config}\n guest spec: {guest_cpu_config}"
    )


def extract_lscpu_info(lscpu_output):
    """
    Extract data fom lscpu command executed guest

    Args:
        lscpu_output (str): output of lscpu command

    Returns:
        dict with command output for CPU threads, cores, sockets, numa nodes, CPU name and CPU flags.

    Example:
        {'threads': '1',
         'cores': '4',
         'sockets': '1',
         'numa_nodes': '1',
         'model_name': 'Intel(R) Xeon(R) Gold 6238L CPU @ 2.10GHz',
         'cpu_flags': 'fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge'}
    """

    return re.search(
        r".*Thread\(s\) per core:\s+(?P<threads>\d+).*Core\(s\) per socket:\s+(?P<cores>\d+).*Socket\(s\):\s+"
        r"(?P<sockets>\d+).*NUMA node\(s\):\s+(?P<numa_nodes>\d+).*Model name:\s+(?P<model_name>.*)\nStepping"
        r".*Flags:\s+(?P<cpu_flags>.*).*",
        lscpu_output,
        re.DOTALL,
    ).groupdict()


def assert_libvirt_cpu_host_passthrough(vm, vmi_xml_dict):
    host_passthrough = "host-passthrough"
    LOGGER.info(f"Verify {vm.name} CPU {host_passthrough}")
    libvirt_cpu_mode = vmi_xml_dict["cpu"]["@mode"]
    assert (
        libvirt_cpu_mode == host_passthrough
    ), f"CPU mode is {libvirt_cpu_mode}, expected: {host_passthrough}, "


def assert_vm_cpu_matches_node_cpu(node_lscpu_configuration, guest_cpu_config):
    # Verify host-passthrough configuration is enforced and VM CPU model is identical to the host's CPU model
    node_cpu_model = node_lscpu_configuration["model_name"]
    guest_cpu_model = guest_cpu_config["model_name"]
    assert (
        node_cpu_model == guest_cpu_model
    ), f"Guest CPU model {guest_cpu_model} does not match host CPU model {node_cpu_model}"


@pytest.fixture(scope="class")
def sap_hana_data_volume_templates(sap_hana_template):
    data_volume_templates = deepcopy(
        sap_hana_template.instance.to_dict()["objects"][0]["spec"][
            "dataVolumeTemplates"
        ]
    )[0]
    data_volume_templates["metadata"]["name"] = SAP_HANA_VM_NAME
    # TODO: remove once dataSources are used (4.11, https://issues.redhat.com/browse/CNV-15772)
    data_volume_templates["spec"]["storage"][
        "storageClassName"
    ] = StorageClass.Types.NFS

    if get_bug_status(bug=2039686) not in BUG_STATUS_CLOSED:
        data_volume_templates["spec"]["source"]["registry"][
            "url"
        ] = "docker://registry.redhat.io/rhel8/rhel-guest-image:8.4.0"
    return data_volume_templates


@pytest.fixture(scope="class")
def sap_hana_cloud_init():
    rhsm_clout_init = generate_rhsm_cloud_init_data()
    # Allow connectivity on all interfaces
    rhsm_clout_init["userData"]["bootcmd"].append(
        "sysctl -w net.ipv4.conf.all.rp_filter=0"
    )
    return rhsm_clout_init


@pytest.fixture(scope="class")
def rhsm_created_secret_scope_class(namespace):
    yield from generate_rhsm_secret(namespace=namespace)


@pytest.fixture(scope="class")
def sriov_network_node_policy(admin_client, sriov_namespace):
    """SriovNetworkNodePolicy (named "sriov-network-policy") is deployed as part of SAP HANA jenkins job"""
    sriov_available_node_policies = [
        policy
        for policy in SriovNetworkNodePolicy.get(
            dyn_client=admin_client,
            namespace=sriov_namespace.name,
        )
        if "sriov-network-policy" in policy.name
    ]
    assert (
        len(sriov_available_node_policies) == REQUIRED_NUMBER_OF_NETWORKS
    ), f"Cluster should be configured with {REQUIRED_NUMBER_OF_NETWORKS} SR-IOV networks"

    return sriov_available_node_policies


@pytest.fixture(scope="class")
def sriov_nads(namespace, sriov_network_node_policy, sriov_namespace):
    nads_list = []
    for idx in range(REQUIRED_NUMBER_OF_NETWORKS):
        with network_nad(
            nad_type=SRIOV,
            nad_name=f"sriov-net-{idx + 1}",
            sriov_resource_name=sriov_network_node_policy[
                idx
            ].instance.spec.resourceName,
            namespace=sriov_namespace,
            sriov_network_namespace=namespace.name,
            macspoofchk="off",
            teardown=False,
        ) as nad:
            nads_list.append(nad)
    yield nads_list
    [nad.clean_up() for nad in nads_list]


@pytest.fixture(scope="class")
def sap_hana_vm(
    unprivileged_client,
    namespace,
    sriov_nads,
    sap_hana_template_labels,
    sap_hana_data_volume_templates,
    sap_hana_node,
    sap_hana_cloud_init,
):
    with SAPHANAVirtaulMachine(
        name=SAP_HANA_VM_NAME,
        namespace=namespace.name,
        client=unprivileged_client,
        labels=sap_hana_template_labels,
        data_volume_template=sap_hana_data_volume_templates,
        node_selector=sap_hana_node.hostname,  # TODO: Use label (https://bugzilla.redhat.com/show_bug.cgi?id=2039691)
        cloud_init_data=sap_hana_cloud_init,
        sriov_nads=sriov_nads,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def sap_hana_node(schedulable_nodes):
    hana_nodes = [
        node for node in schedulable_nodes if HANA_NODE_ROLE in node.labels.keys()
    ]
    if hana_nodes:
        return hana_nodes[0]


@pytest.fixture(scope="class")
def skip_if_not_hana_cluster(skip_if_no_cpumanager_workers, sap_hana_node):
    if not sap_hana_node:
        pytest.skip(f"No node is marked with sap role {HANA_NODE_ROLE}")


@pytest.fixture(scope="class")
def sap_hana_node_lscpu_configuration(utility_pods, sap_hana_node):
    lscpu_output = ExecCommandOnPod(utility_pods=utility_pods, node=sap_hana_node).exec(
        command=LSCPU_CMD
    )
    return extract_lscpu_info(lscpu_output=lscpu_output)


@pytest.fixture()
def hana_node_invtsc_labels(sap_hana_node):
    node_invtsc_labels = {
        label_name: label_value
        for label_name, label_value in sap_hana_node.labels.items()
        if INVTSC in label_name
    }
    assert (
        node_invtsc_labels
    ), f"Node {sap_hana_node.name} does not have {INVTSC} labels."
    assert all(
        [label_value == "true" for label_value in node_invtsc_labels.values()]
    ), f"Some {INVTSC} lables are disabled: {node_invtsc_labels}"


@pytest.fixture()
def hana_node_cpu_tsc_frequency_labels(sap_hana_node):
    tsc_frequency = "tsc-frequency"
    node_tsc_frequency_labels = get_node_labels_by_name_subset(
        node=sap_hana_node, label_name_subset=tsc_frequency
    )
    assert_node_label_exists(node=sap_hana_node, label_name=tsc_frequency)
    assert (
        int(node_tsc_frequency_labels[f"{CPU_TIMER_LABEL_PREFIX}/{tsc_frequency}"]) > 0
    ), f"Wrong {tsc_frequency}, value: {node_tsc_frequency_labels}"


@pytest.fixture()
def hana_node_nonstop_tsc_cpu_flag(sap_hana_node_lscpu_configuration, sap_hana_node):
    nonstop_tsc_flag = "nonstop_tsc"
    node_cpu_flags = sap_hana_node_lscpu_configuration["cpu_flags"]
    assert (
        nonstop_tsc_flag in node_cpu_flags
    ), f"Node {sap_hana_node.name} does not have {nonstop_tsc_flag} flag; existing flags: {node_cpu_flags}"


@pytest.fixture()
def hana_node_cpu_tsc_scalable_label(sap_hana_node):
    tsc_scalable = "tsc-scalable"
    node_tsc_scalable_label = get_node_labels_by_name_subset(
        node=sap_hana_node, label_name_subset=tsc_scalable
    )
    assert_node_label_exists(node=sap_hana_node, label_name=tsc_scalable)
    assert (
        node_tsc_scalable_label[f"{CPU_TIMER_LABEL_PREFIX}/{tsc_scalable}"] == "true"
    ), f"{tsc_scalable} is disabled on {sap_hana_node.name}"


@pytest.fixture(scope="module")
def sap_hana_template_labels():
    return Template.generate_template_labels(
        **{
            "os": "rhel8.4",
            "workload": Template.Workload.SAPHANA,
            "flavor": Template.Flavor.TINY,
        }
    )


@pytest.fixture(scope="module")
def sap_hana_template(admin_client, sap_hana_template_labels):
    return get_template_by_labels(
        admin_client=admin_client, template_labels=sap_hana_template_labels
    )


@pytest.fixture(scope="class")
def vmi_domxml(sap_hana_vm):
    return sap_hana_vm.vmi.xml_dict["domain"]


@pytest.fixture(scope="class")
def guest_lscpu_configuration(sap_hana_vm):
    guest_lscpu_output = run_ssh_commands(
        host=sap_hana_vm.ssh_exec, commands=[LSCPU_CMD]
    )[0]
    return extract_lscpu_info(lscpu_output=guest_lscpu_output)


class TestSAPHANATemplate:
    @pytest.mark.polarion("CNV-7623")
    def test_sap_hana_template_validation_rules(self, sap_hana_template):
        assert sap_hana_template.instance.objects[0].metadata.annotations[
            f"{sap_hana_template.ApiGroup.VM_KUBEVIRT_IO}/validations"
        ], "HANA template does not have validation rules."

    @pytest.mark.polarion("CNV-7759")
    def test_sap_hana_template_machine_type(
        self, sap_hana_template, machine_type_from_kubevirt_config
    ):
        sap_hana_template_machine_type = sap_hana_template.instance.objects[
            0
        ].spec.template.spec.domain.machine.type
        assert sap_hana_template_machine_type == machine_type_from_kubevirt_config, (
            f"Hana template machine type '{sap_hana_template_machine_type or None}' does not match expected type "
            f"{machine_type_from_kubevirt_config}"
        )

    @pytest.mark.polarion("CNV-7852")
    def test_sap_hana_template_no_evict_strategy(self, sap_hana_template):
        sap_hana_template_evict_strategy = sap_hana_template.instance.objects[
            0
        ].spec.template.spec.evictionStrategy
        assert not sap_hana_template_evict_strategy, (
            "HANA template should not have evictionStrategy, current value in template: "
            f"{sap_hana_template_evict_strategy}"
        )

    @pytest.mark.polarion("CNV-7758")
    def test_sap_hana_template_provider_support_annotations(self, sap_hana_template):
        template_failed_annotations = []
        template_annotations = sap_hana_template.instance.metadata.annotations
        template_api_group = sap_hana_template.ApiGroup.TEMPLATE_KUBEVIRT_IO
        if (
            template_annotations[f"{template_api_group}/provider-support-level"]
            != "Experimental"
        ):
            template_failed_annotations.append("provider-support-level")
        if (
            template_annotations[f"{template_api_group}/provider-url"]
            != "https://www.redhat.com"
        ):
            template_failed_annotations.append("provider-url")
        if (
            template_annotations[f"{template_api_group}/provider"]
            != "Red Hat - Tech Preview"
        ):
            template_failed_annotations.append("provide")
        assert not template_failed_annotations, (
            f"HANA template failed annotations: {template_failed_annotations}, "
            f"template annotations: {template_annotations}"
        )


@pytest.mark.sap_hana
@pytest.mark.usefixtures(
    "skip_if_not_hana_cluster",
    "rhsm_created_secret_scope_class",
)
class TestSAPHANAVirtualMachine:
    @pytest.mark.dependency(name=SAP_HANA_VM_TEST_NAME)
    @pytest.mark.polarion("CNV-7622")
    def test_sap_hana_console(self, sap_hana_vm):
        wait_for_console(
            vm=sap_hana_vm,
            console_impl=console.RHEL,
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7760")
    def test_sap_hana_vm_cpu_configuration(
        self,
        sap_hana_vm,
        vmi_domxml,
        guest_lscpu_configuration,
        sap_hana_template,
        utility_pods,
    ):
        verify_vm_cpu_topology(
            vm=sap_hana_vm,
            vmi_xml_dict=vmi_domxml,
            guest_cpu_config=guest_lscpu_configuration,
            template=sap_hana_template,
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7870")
    def test_sap_hana_vm_cpu_host_passthrough(
        self,
        sap_hana_vm,
        vmi_domxml,
        guest_lscpu_configuration,
        sap_hana_node_lscpu_configuration,
    ):
        assert_libvirt_cpu_host_passthrough(
            vm=sap_hana_vm,
            vmi_xml_dict=vmi_domxml,
        )
        assert_vm_cpu_matches_node_cpu(
            node_lscpu_configuration=sap_hana_node_lscpu_configuration,
            guest_cpu_config=guest_lscpu_configuration,
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7763")
    def test_sap_hana_vm_invtsc_feature(
        self,
        hana_node_invtsc_labels,
        hana_node_cpu_tsc_frequency_labels,
        hana_node_cpu_tsc_scalable_label,
        hana_node_nonstop_tsc_cpu_flag,
        vmi_domxml,
    ):
        invtsc_libvirt_name = vmi_domxml["cpu"]["feature"]["@name"]
        invtsc_libvirt_policy = vmi_domxml["cpu"]["feature"]["@policy"]
        expected_policy = "require"
        assert (
            invtsc_libvirt_name == INVTSC and invtsc_libvirt_policy == expected_policy
        ), (
            f"wrong {INVTSC} policy in libvirt: policy name: {invtsc_libvirt_name}, value: {invtsc_libvirt_policy}, "
            f"expected: {expected_policy}"
        )
