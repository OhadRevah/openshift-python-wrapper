# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV tests
"""
import base64
import logging
import os
import os.path
import re
import shutil
from configparser import ConfigParser
from contextlib import contextmanager
from subprocess import PIPE, CalledProcessError, Popen, check_output

import bcrypt
import kubernetes
import pytest
import rrmngmnt
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config
from resources.cluster_service_version import ClusterServiceVersion
from resources.configmap import ConfigMap
from resources.daemonset import DaemonSet
from resources.datavolume import DataVolume
from resources.mutating_webhook_config import MutatingWebhookConfiguration
from resources.namespace import Namespace
from resources.network_attachment_definition import NetworkAttachmentDefinition
from resources.node import Node
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from resources.node_network_state import NodeNetworkState
from resources.oauth import OAuth
from resources.persistent_volume import PersistentVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.pod import Pod
from resources.secret import Secret
from resources.service_account import ServiceAccount
from resources.sriov_network_node_policy import SriovNetworkNodePolicy
from resources.sriov_network_node_state import SriovNetworkNodeState
from resources.template import Template
from resources.utils import TimeoutExpiredError, TimeoutSampler
from resources.virtual_machine import (
    VirtualMachine,
    VirtualMachineInstance,
    VirtualMachineInstanceMigration,
)
from utilities import console
from utilities.infra import ClusterHosts, create_ns
from utilities.network import OVS, EthernetNetworkConfigurationPolicy, network_nad
from utilities.storage import data_volume
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    RHEL_CLOUD_INIT_PASSWORD,
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    WinRMcliPod,
    enable_ssh_service_in_vm,
    fedora_vm_body,
    generate_yaml_from_template,
    kubernetes_taint_exists,
    nmcli_add_con_cmds,
    wait_for_vm_interfaces,
    wait_for_windows_vm,
)


LOGGER = logging.getLogger(__name__)
UNPRIVILEGED_USER = "unprivileged-user"
UNPRIVILEGED_PASSWORD = "unprivileged-password"
TEST_LOG_FILE = "pytest-tests.log"
TEST_COLLECT_INFO_DIR = "tests-collected-info"
RESOURCES_TO_COLLECT_INFO = [
    DataVolume,
    PersistentVolume,
    PersistentVolumeClaim,
    VirtualMachine,
    VirtualMachineInstance,
    VirtualMachineInstanceMigration,
    NetworkAttachmentDefinition,
    NodeNetworkConfigurationPolicy,
    NodeNetworkState,
]

PODS_TO_COLLECT_INFO = [
    "virt-launcher",
    "virt-api",
    "virt-controller",
    "virt-handler",
    "virt-template-validator",
    "cdi-importer",
]
TESTS_MARKERS = [
    "smoke",
    "destructive",
    "ci",
    "tier3",
]


def _get_client():
    return DynamicClient(client=kubernetes.config.new_client_from_config())


def _separator(symbol_, val=None):
    terminal_width = shutil.get_terminal_size(fallback=(120, 40))[0]
    if not val:
        return f"{symbol_ * terminal_width}"

    sepa = int((terminal_width - len(val) - 2) // 2)
    return f"{symbol_ * sepa} {val} {symbol_ * sepa}"


def pytest_addoption(parser):
    parser.addoption(
        "--upgrade", choices=["cnv", "ocp"], help="Run OCP or CNV upgrade tests"
    )
    parser.addoption("--cnv-version", help="CNV version to upgrade to")
    parser.addoption("--ocp-image", help="OCP image to upgrade to")
    parser.addoption("--storage-class-matrix", help="Storage class matrix to use")
    parser.addoption("--bridge-device-matrix", help="Bridge device matrix to use")
    parser.addoption("--rhel-os-matrix", help="RHEL OS matrix to use")
    parser.addoption("--windows-os-matrix", help="Windows OS matrix to use")
    parser.addoption("--fedora-os-matrix", help="Fedora OS matrix to use")
    parser.addoption(
        "--upgrade_resilience",
        action="store_true",
        help="If provided, run upgrade with disruptions",
    )


def pytest_cmdline_main(config):
    if config.getoption("upgrade") == "ocp":
        if not config.getoption("ocp_image"):
            raise ValueError("Running with --upgrade ocp: Missing --ocp-image")

    if config.getoption("upgrade") == "cnv":
        if not config.getoption("cnv_version"):
            raise ValueError("Running with --upgrade cnv: Missing --cnv-version")


def pytest_collection_modifyitems(session, config, items):
    """
    Add polarion test case it from tests to junit xml
    """
    for item in items:
        scope_match = re.compile(r"__(module|class|function)__$")
        for fixture_name in [
            fixture_name
            for fixture_name in item.fixturenames
            if "_matrix" in fixture_name
        ]:
            matrix_name = scope_match.sub("", fixture_name)
            values = re.findall("(#.*?#)", item.name)
            for value in values:
                value = value.strip("#").strip("#")
                for param in py_config[matrix_name]:
                    if isinstance(param, dict):
                        param = [*param][0]

                    if value == param:
                        item.user_properties.append(
                            (f"polarion-parameter-{matrix_name}", value)
                        )

        for marker in item.iter_markers(name="polarion"):
            test_id = marker.args[0]
            item.user_properties.append(("polarion-testcase-id", test_id))

        for marker in item.iter_markers(name="bugzilla"):
            test_id = marker.args[0]
            item.user_properties.append(("bugzilla", test_id))

        for marker in item.iter_markers(name="jira"):
            test_id = marker.args[0]
            item.user_properties.append(("jira", test_id))

        for _ in item.iter_markers(name="upgrade_resilience"):
            item.user_properties.append(
                (
                    "polarion-parameter-upgrade_resilience",
                    config.getoption("upgrade_resilience"),
                )
            )

        # Add tier2 marker for tests without any marker.
        markers = [mark.name for mark in list(item.iter_markers())]
        if not [mark for mark in markers if mark in TESTS_MARKERS]:
            item.add_marker("tier2")

    #  Collect only 'upgrade' tests when running pytest with --upgrade
    upgrade_tests = [item for item in items if "upgrade" in item.keywords]
    non_upgrade_tests = [item for item in items if "upgrade" not in item.keywords]
    if config.getoption("--upgrade"):
        discard = non_upgrade_tests
        keep = upgrade_tests

    else:
        discard = upgrade_tests
        keep = non_upgrade_tests

    items[:] = keep
    config.hook.pytest_deselected(items=discard)


def pytest_runtest_makereport(item, call):
    """
    incremental tests implementation
    """
    if "incremental" in item.keywords:
        if call.excinfo is not None:
            parent = item.parent
            parent._previousfailed = item


def pytest_runtest_setup(item):
    """
    Use incremental
    """
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail("previous test failed (%s)" % previousfailed.name)


def pytest_generate_tests(metafunc):
    scope_match = re.compile(r"__(module|class|function)__$")
    for fixture_name in [
        fname for fname in metafunc.fixturenames if "_matrix" in fname
    ]:
        scope = scope_match.findall(fixture_name)
        if not scope:
            raise ValueError(f"{fixture_name} is missing scope (__<scope>__)")

        matrix_name = scope_match.sub("", fixture_name)
        _matrix_params = py_config.get(matrix_name)
        if not _matrix_params:
            raise ValueError(f"{matrix_name} is missing in config file")

        matrix_params = (
            _matrix_params if isinstance(_matrix_params, list) else [_matrix_params]
        )
        ids = []
        for matrix_param in matrix_params:
            if isinstance(matrix_param, dict):
                ids.append(f"#{[*matrix_param][0]}#")
            else:
                ids.append(f"#{matrix_param}#")

        metafunc.parametrize(
            fixture_name, matrix_params, ids=ids, scope=scope[0],
        )


def pytest_runtest_logreport(report):
    is_setup = report.when == "setup"
    is_test = report.when == "call"
    scope_section_separator = f"\n{_separator(symbol_='-', val=report.when.upper())}\n"
    test_status_str = f"\n\nSTATUS: {report.outcome.upper()}\n"

    with open(TEST_LOG_FILE, "a", buffering=1) as fd:
        if is_setup:
            fd.write(f"\n{_separator(val=report.nodeid, symbol_='#')}\n")

        log_section = [
            section[1] for section in report.sections if report.when in section[0]
        ]

        if log_section:
            fd.write(scope_section_separator)
            fd.write(f"{log_section[0]}")
        else:
            if is_test:
                fd.write(scope_section_separator)

        if is_test and not report.failed:
            fd.write(test_status_str)

        if report.failed:
            if not log_section and not is_test:
                fd.write(scope_section_separator)

            fd.write(test_status_str)
            fd.write(f"{report.longreprtext}\n")


def pytest_sessionstart(session):
    # Save the default storage_class_matrix before it is updated
    # with runtime storage_class_matrix value(s)
    py_config["system_storage_class_matrix"] = py_config["storage_class_matrix"]

    matrix_addoptions = [
        matrix
        for matrix in session.config.invocation_params.args
        if "-matrix=" in matrix
    ]
    for matrix_addoption in matrix_addoptions:
        items_list = []
        key, vals = matrix_addoption.split("=")
        key = key.strip("--").replace("-", "_")
        vals = vals.split(",")

        for val in vals:
            for item in py_config[key]:
                if isinstance(item, dict):
                    # Extract only the dicts item which has the requested key from
                    if [*item][0] == val:
                        items_list.append(item)

                if isinstance(item, str):
                    # Extract only the items item which has the requested key from
                    items_list.append(val)

        py_config[key] = items_list


def pytest_sessionfinish(session, exitstatus):
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    passed_str = "passed"
    skipped_str = "skipped"
    failed_str = "failed"

    passed = len(reporter.stats.get(passed_str, []))
    skipped = len(reporter.stats.get(skipped_str, []))
    failed = len(reporter.stats.get(failed_str, []))
    summary = f"{passed} {passed_str}, {skipped} {skipped_str}, {failed} {failed_str}"

    with open(TEST_LOG_FILE, "a", buffering=1) as fd:
        fd.write(f"\n{_separator(symbol_='-', val=summary)}")


def pytest_exception_interact(node, call, report):
    if os.environ.get("CNV_TEST_COLLECT_LOGS", "0") != "1":
        return

    try:
        dyn_client = _get_client()
        test_dir = os.path.join(TEST_COLLECT_INFO_DIR, node.name, call.when)
        pods_dir = os.path.join(test_dir, "Pods")
        os.makedirs(test_dir, exist_ok=True)
        os.makedirs(pods_dir, exist_ok=True)

        for _resources in RESOURCES_TO_COLLECT_INFO:
            resource_dir = os.path.join(test_dir, _resources.__name__)
            for resource_obj in _resources.get(dyn_client=dyn_client):
                if not os.path.isdir(resource_dir):
                    os.makedirs(resource_dir, exist_ok=True)

                with open(
                    os.path.join(resource_dir, f"{resource_obj.name}.yaml"), "w"
                ) as fd:
                    fd.write(resource_obj.instance.to_str())

        for pod in Pod.get(dyn_client=dyn_client):
            kwargs = {}
            for pod_prefix in PODS_TO_COLLECT_INFO:
                if pod.name.startswith(pod_prefix):
                    if pod_prefix == "virt-launcher":
                        kwargs = {"container": "compute"}

                    with open(os.path.join(pods_dir, f"{pod.name}.log"), "w") as fd:
                        fd.write(pod.log(**kwargs))

                    with open(os.path.join(pods_dir, f"{pod.name}.yaml"), "w") as fd:
                        fd.write(pod.instance.to_str())
    except Exception:
        return


@pytest.fixture(scope="session", autouse=True)
def tests_log_file():
    with open(TEST_LOG_FILE, "w"):
        pass


@pytest.fixture(scope="session", autouse=True)
def tests_collect_info_dir():
    shutil.rmtree(TEST_COLLECT_INFO_DIR, ignore_errors=True)
    os.makedirs(TEST_COLLECT_INFO_DIR)


def login_to_account(api_address, user, password=None):
    """
    Helper function for login. Raise exception if login failed
    """
    stop_errors = [
        "connect: no route to host",
        "x509: certificate signed by unknown authority",
    ]
    login_command = f"oc login {api_address} -u {user}"
    if password:
        login_command += f" -p {password}"

    samples = TimeoutSampler(
        timeout=60,
        sleep=3,
        exceptions=CalledProcessError,
        func=Popen,
        args=login_command,
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
    )
    try:
        for sample in samples:
            LOGGER.info(
                f"Trying to login to {user} user shell. Login command: {login_command}"
            )
            login_result = sample.communicate()
            if sample.returncode == 0:
                LOGGER.info(f"Login to {user} user shell - success")
                return True

            LOGGER.warning(
                f"Login to unprivileged user - failed due to the following error: "
                f"{login_result[0].decode('utf-8')} {login_result[1].decode('utf-8')}"
            )
            if [err for err in stop_errors if err in login_result[1].decode("utf-8")]:
                break

    except TimeoutExpiredError:
        return False


@pytest.fixture(scope="session", autouse=True)
def junitxml_polarion(record_testsuite_property):
    """
    Add polarion needed attributes to junit xml

    export as os environment:
    POLARION_CUSTOM_PLANNEDIN
    POLARION_TESTRUN_ID
    POLARION_TIER
    """
    record_testsuite_property("polarion-custom-isautomated", "True")
    record_testsuite_property("polarion-testrun-status-id", "inprogress")
    record_testsuite_property(
        "polarion-custom-plannedin", os.getenv("POLARION_CUSTOM_PLANNEDIN")
    )
    record_testsuite_property("polarion-user-id", "cnvqe")
    record_testsuite_property("polarion-project-id", "CNV")
    record_testsuite_property("polarion-response-myproduct", "cnv-test-run")
    record_testsuite_property("polarion-testrun-id", os.getenv("POLARION_TESTRUN_ID"))
    record_testsuite_property("polarion-custom-env_tier", os.getenv("POLARION_TIER"))
    record_testsuite_property("polarion-custom-env_os", os.getenv("POLARION_OS"))


@pytest.fixture(scope="session", autouse=True)
def default_client():
    """
    Get DynamicClient
    """
    return _get_client()


@pytest.fixture(scope="session")
def unprivileged_secret(default_client):
    if py_config["distribution"] == "upstream" or py_config.get(
        "no_unprivileged_client"
    ):
        yield

    else:
        password = UNPRIVILEGED_PASSWORD.encode()
        enc_password = bcrypt.hashpw(password, bcrypt.gensalt(5, prefix=b"2a")).decode()
        crypto_credentials = f"{UNPRIVILEGED_USER}:{enc_password}".encode()
        with Secret(
            name="htpass-secret",
            namespace="openshift-config",
            htpasswd=base64.b64encode(crypto_credentials).decode(),
        ) as secret:
            yield secret


@pytest.fixture(scope="session")
def unprivileged_client(default_client, unprivileged_secret):
    """
    Provides none privilege API client
    """
    # To disable unprivileged_client pass --tc=no_unprivileged_client:True to pytest commandline.
    if not unprivileged_secret:
        yield

    else:
        token = None
        kube_config_path = os.path.join(os.path.expanduser("~"), ".kube/config")
        kubeconfig_env = os.environ.get("KUBECONFIG")
        kube_config_exists = os.path.isfile(kube_config_path)
        if kubeconfig_env and kube_config_exists:
            raise ValueError(
                f"Both KUBECONFIG {kubeconfig_env} and {kube_config_path} exists. "
                f"Only one should be used, "
                f"either remove {kube_config_path} file or unset KUBECONFIG"
            )

        # Update identity provider
        identity_provider_config = OAuth(name="cluster")
        identity_provider_config.update(
            resource_dict={
                "metadata": {"name": identity_provider_config.name},
                "spec": {
                    "identityProviders": [
                        {
                            "name": "htpasswd_provider",
                            "mappingMethod": "claim",
                            "type": "HTPasswd",
                            "htpasswd": {"fileData": {"name": "htpass-secret"}},
                        }
                    ]
                },
            }
        )

        current_user = (
            check_output("oc whoami", shell=True).decode().strip()
        )  # Get current admin account
        if kube_config_exists:
            os.environ["KUBECONFIG"] = ""

        if login_to_account(
            api_address=default_client.configuration.host,
            user=UNPRIVILEGED_USER,
            password=UNPRIVILEGED_PASSWORD,
        ):  # Login to unprivileged account
            token = (
                check_output("oc whoami -t", shell=True).decode().strip()
            )  # Get token
            token_auth = {
                "api_key": {"authorization": f"Bearer {token}"},
                "host": default_client.configuration.host,
                "verify_ssl": True,
                "ssl_ca_cert": default_client.configuration.ssl_ca_cert,
            }
            configuration = kubernetes.client.Configuration()
            for k, v in token_auth.items():
                setattr(configuration, k, v)

            if kubeconfig_env:
                os.environ["KUBECONFIG"] = kubeconfig_env

            login_to_account(
                api_address=default_client.configuration.host, user=current_user.strip()
            )  # Get back to admin account

            k8s_client = kubernetes.client.ApiClient(configuration)
            yield DynamicClient(k8s_client)
        else:
            yield

        # Teardown
        if token:
            try:
                if kube_config_exists:
                    os.environ["KUBECONFIG"] = ""

                login_to_account(
                    api_address=default_client.configuration.host,
                    user=UNPRIVILEGED_USER,
                    password=UNPRIVILEGED_PASSWORD,
                )  # Login to unprivileged account
                LOGGER.info("Logout unprivileged_client")
                Popen(args=["oc", "logout"], stdout=PIPE, stderr=PIPE).communicate()
            finally:
                if kubeconfig_env:
                    os.environ["KUBECONFIG"] = kubeconfig_env

                login_to_account(
                    api_address=default_client.configuration.host,
                    user=current_user.strip(),
                )  # Get back to admin account


@pytest.fixture(scope="session")
def schedulable_node_ips(schedulable_nodes):
    """
    Store all kubevirt.io/schedulable=true IPs
    """
    node_ips = {}
    for node in schedulable_nodes:
        for addr in node.instance.status.addresses:
            if addr.type == "InternalIP":
                node_ips[node.name] = addr.address
    return node_ips


@pytest.fixture(scope="session")
def skip_when_one_node(schedulable_nodes):
    if len(schedulable_nodes) < 2:
        pytest.skip(msg="Test requires at least 2 nodes")


@pytest.fixture(scope="session")
def nodes(default_client):
    yield list(Node.get(dyn_client=default_client))


@pytest.fixture(scope="session")
def schedulable_nodes(nodes):
    schedulable_label = "kubevirt.io/schedulable"
    yield [
        node
        for node in nodes
        if schedulable_label in node.labels.keys()
        and node.labels[schedulable_label] == "true"
        and not node.instance.spec.unschedulable
        and not kubernetes_taint_exists(node)
        and node.kubelet_ready
    ]


@pytest.fixture(scope="session")
def masters(nodes):
    yield [
        node for node in nodes if "node-role.kubernetes.io/master" in node.labels.keys()
    ]


@pytest.fixture(scope="session")
def utility_daemonset(default_client):
    """
    Deploy utility daemonset into the kube-system namespace.

    This daemonset deploys a pod on every node with hostNetwork and the main usage is to run commands on the hosts.
    For example to create linux bridge and other components related to the host configuration.
    """
    with UtilityDaemonSet(name="utility", namespace="kube-system") as ds:
        ds.wait_until_deployed()
        yield ds


@pytest.fixture(scope="session")
def utility_pods(schedulable_nodes, utility_daemonset, default_client):
    """
    Get utility pods.
    When the tests start we deploy a pod on every host in the cluster using a daemonset.
    These pods have a label of cnv-test=utility and they are privileged pods with hostnetwork=true
    """
    # get only pods that running on schedulable_nodes.
    pods = list(Pod.get(default_client, label_selector="cnv-test=utility"))
    return [
        pod
        for pod in pods
        if pod.node.name in [node.name for node in schedulable_nodes]
    ]


@pytest.fixture(scope="session")
def workers_ssh_executors(rhel7_workers, utility_pods):
    executors = {}
    ssh_key = os.getenv("HOST_SSH_KEY")
    for pod in utility_pods:
        host = rrmngmnt.Host(ip=pod.instance.status.podIP)
        if ssh_key:
            host.executor_factory = rrmngmnt.ssh.RemoteExecutorFactory(use_pkey=True)

        host_user = rrmngmnt.user.User(
            name="root" if rhel7_workers else "core", password=None
        )
        host._set_executor_user(user=host_user)
        host.add_user(user=host_user)
        executors[pod.node.name] = host

    return executors


@pytest.fixture(scope="session")
def node_physical_nics(default_client, utility_pods, workers_ssh_executors):
    if is_openshift(default_client):
        return {
            node: workers_ssh_executors[node].network.all_interfaces()
            for node in workers_ssh_executors.keys()
        }
    else:
        return network_interfaces_k8s(utility_pods)


def network_interfaces_k8s(network_utility_pods):
    interfaces = {}
    for pod in network_utility_pods:
        node = pod.instance.spec.nodeName
        output = pod.execute(
            ["bash", "-c", "ls -la /sys/class/net | grep pci | grep -o '[^/]*$'"]
        ).split("\n")
        interfaces[node] = list(filter(None, output))  # Filter out empty lines

    return interfaces


@pytest.fixture(scope="session")
def nodes_active_nics(schedulable_nodes, node_physical_nics):
    """
    Get nodes active NICs.
    First NIC is management NIC
    """

    def _insert_first(ifaces, primary, iface):
        if primary:
            ifaces.insert(0, iface.name)
        else:
            ifaces.append(iface.name)

    nodes_nics = {}
    for node in schedulable_nodes:
        ifaces = []
        nns = NodeNetworkState(name=node.name)
        default_routes = [
            route for route in nns.routes.running if route.destination == "0.0.0.0/0"
        ]
        lowest_metric = min([route.metric for route in default_routes])
        primary_iface_name = [
            route["next-hop-interface"]
            for route in default_routes
            if route.metric == lowest_metric
        ]

        for iface in nns.interfaces:
            primary = primary_iface_name == iface.name
            if iface.type == "ethernet":
                # In OVN deployment we get extra auto generated OVN interfaces so we need to exclude them
                if iface.name not in node_physical_nics[node.name]:
                    continue

                _insert_first(ifaces=ifaces, primary=primary, iface=iface)

            if iface.type == "ovs-bridge":
                if iface.state == "up":
                    _insert_first(ifaces=ifaces, primary=primary, iface=iface)

        nodes_nics[node.name] = ifaces

    return nodes_nics


@pytest.fixture(scope="session")
def multi_nics_nodes(nodes_active_nics):
    """
    Check if nodes has more then 1 active NIC
    """
    return min(len(nics) for nics in nodes_active_nics.values()) > 2


@pytest.fixture(scope="session")
def skip_if_no_multinic_nodes(multi_nics_nodes):
    if not multi_nics_nodes:
        pytest.skip("Only run on multi NICs node")


class UtilityDaemonSet(DaemonSet):
    def to_dict(self):
        res = super().to_dict()
        res.update(
            generate_yaml_from_template(
                file_=os.path.join(os.path.dirname(__file__), "utility-daemonset.yaml")
            )
        )
        return res


@pytest.fixture(scope="session")
def kmp_vm_label(default_client):
    kmp_vm_webhook = "mutatevirtualmachines.kubemacpool.io"
    kmp_webhook_config = MutatingWebhookConfiguration(
        client=default_client, name="kubemacpool-mutator"
    )

    for webhook in kmp_webhook_config.instance.to_dict()["webhooks"]:
        if webhook["name"] == kmp_vm_webhook:
            return webhook["namespaceSelector"]["matchLabels"]

    raise Exception(f"Webhook {kmp_vm_webhook} was not found")


@pytest.fixture(scope="module")
def namespace(request, unprivileged_client, default_client, kmp_vm_label):
    """ Generate namespace from the test's module name """
    client = True
    if hasattr(request, "param"):
        client = request.param.get("unprivileged_client", True)

    name = (
        request.fspath.strpath.split(f"{os.path.dirname(__file__)}/")[1]
        .strip(".py")
        .replace("/", "-")
        .replace("_", "-")
    )[-63:]
    yield from create_ns(
        client=unprivileged_client if client else None,
        name=name.split("-", 1)[-1],
        admin_client=default_client,
        kmp_vm_label=kmp_vm_label,
    )


@pytest.fixture(scope="session")
def skip_upstream():
    if py_config["distribution"] == "upstream":
        pytest.skip(
            msg="Running only on downstream,"
            "Reason: HTTP/Registry servers are not available for upstream",
        )


@pytest.fixture(scope="session", autouse=True)
def leftovers():
    secret = Secret(name="htpass-secret", namespace="openshift-config")
    ds = UtilityDaemonSet(name="utility", namespace="kube-system")
    for resource_ in (secret, ds):
        try:
            if resource_.instance:
                resource_.delete(wait=True)
        except NotFoundError:
            continue


@pytest.fixture(scope="session")
def workers_type(utility_pods):
    for pod in utility_pods:
        out = pod.execute(
            command=["bash", "-c", "dmesg | grep 'Hypervisor detected' | wc -l"]
        )
        if int(out) > 0:
            return ClusterHosts.Type.VIRTUAL

    return ClusterHosts.Type.PHYSICAL


@pytest.fixture(scope="module")
def skip_if_workers_vms(workers_type):
    if workers_type == ClusterHosts.Type.VIRTUAL:
        pytest.skip(msg="Test should run only BM cluster")


# RHEL 7 specific fixtures
@pytest.fixture(scope="session")
def rhel7_workers(worker_node1):
    # Check only the first Node since mixed rchos and RHEL7 workers in cluster is not supported.
    return re.search(
        r"^Red Hat Enterprise Linux Server 7\.\d",
        worker_node1.instance.status.nodeInfo.osImage,
    )


@pytest.fixture(scope="session")
def skip_rhel7_workers(rhel7_workers):
    if rhel7_workers:
        pytest.skip(msg="Test should skip on RHEL7 workers")


def _skip_ceph_on_rhel7(storage_class, rhel7_workers):
    if storage_class.get("rook-ceph-block"):
        if rhel7_workers:
            pytest.skip(
                msg="Rook-ceph configuration is not supported on RHEL7 workers",
            )


@pytest.fixture(scope="class")
def skip_ceph_on_rhel7(storage_class_matrix__class__, rhel7_workers):
    _skip_ceph_on_rhel7(
        storage_class=storage_class_matrix__class__, rhel7_workers=rhel7_workers
    )


@pytest.fixture(scope="module")
def skip_ceph_on_rhel7_scope_module(storage_class_matrix__module__, rhel7_workers):
    _skip_ceph_on_rhel7(
        storage_class=storage_class_matrix__module__, rhel7_workers=rhel7_workers
    )


@pytest.fixture(scope="session")
def rhel7_ovs_bridge(rhel7_workers, utility_pods):
    if rhel7_workers:
        # All RHEL workers should be with the same configuration, gating info from the first worker.
        connections = utility_pods[0].execute(
            command=["nmcli", "-t", "connection", "show"]
        )
        for connection in connections.splitlines():
            if "ovs-bridge" in connection:
                return connection.split(":")[-1]


@pytest.fixture(scope="session")
def skip_no_rhel7_workers(rhel7_workers):
    if not rhel7_workers:
        pytest.skip(msg="Test should run only with cluster with RTHEL7 workers")


@pytest.fixture(scope="class")
def rhel7_psi_network_config():
    """ RHEL7 network configuration for PSI clusters """

    return {
        "vm_address": "172.16.0.90",
        "helper_vm_address": "172.16.0.91",
        "subnet": "172.16.0.0",
        "default_gw": "172.16.0.1",
        "dns_server": "172.16.0.16",
    }


@pytest.fixture(scope="class")
def network_attachment_definition(
    skip_ceph_on_rhel7, rhel7_ovs_bridge, namespace, rhel7_workers
):
    if rhel7_workers:
        with network_nad(
            nad_type=OVS,
            nad_name="rhel7-nad",
            interface_name=rhel7_ovs_bridge,
            namespace=namespace,
        ) as network_attachment_definition:
            yield network_attachment_definition
    else:
        yield


@pytest.fixture(scope="class")
def network_configuration(
    skip_ceph_on_rhel7, rhel7_workers, network_attachment_definition,
):
    if rhel7_workers:
        return {network_attachment_definition.name: network_attachment_definition.name}


@pytest.fixture()
def data_volume_multi_storage_scope_function(
    request,
    skip_ceph_on_rhel7,
    namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="class")
def data_volume_multi_storage_scope_class(
    request,
    skip_ceph_on_rhel7,
    namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="module")
def data_volume_multi_storage_scope_module(
    request,
    skip_ceph_on_rhel7_scope_module,
    namespace,
    storage_class_matrix__module__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix__module__,
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture()
def data_volume_scope_function(request, namespace, schedulable_nodes):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class=request.param["storage_class"],
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="class")
def data_volume_scope_class(request, namespace, schedulable_nodes):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class=request.param["storage_class"],
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="module")
def data_volume_scope_module(request, namespace, schedulable_nodes):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class=request.param["storage_class"],
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="class")
def cloud_init_data(
    request, skip_ceph_on_rhel7, workers_type, rhel7_workers, rhel7_psi_network_config,
):
    if rhel7_workers:
        bootcmds = nmcli_add_con_cmds(
            workers_type=workers_type,
            iface="eth1",
            ip=rhel7_psi_network_config["vm_address"],
            default_gw=rhel7_psi_network_config["default_gw"],
            dns_server=rhel7_psi_network_config["dns_server"],
        )

        cloud_init_data = (
            RHEL_CLOUD_INIT_PASSWORD
            if "rhel" in request.fspath.strpath
            else FEDORA_CLOUD_INIT_PASSWORD
        )
        cloud_init_data["bootcmd"] = bootcmds

        return cloud_init_data


@pytest.fixture(scope="class")
def bridge_attached_helper_vm(
    workers_type,
    skip_ceph_on_rhel7,
    rhel7_workers,
    worker_node1,
    namespace,
    unprivileged_client,
    network_attachment_definition,
    rhel7_psi_network_config,
):
    if rhel7_workers:
        name = "helper-vm"
        networks = {
            network_attachment_definition.name: network_attachment_definition.name
        }

        bootcmds = nmcli_add_con_cmds(
            workers_type=workers_type,
            iface="eth1",
            ip=rhel7_psi_network_config["helper_vm_address"],
            default_gw=rhel7_psi_network_config["default_gw"],
            dns_server=rhel7_psi_network_config["dns_server"],
        )

        cloud_init_data = FEDORA_CLOUD_INIT_PASSWORD
        cloud_init_data["bootcmd"] = bootcmds

        # On PSI, set DHCP server configuration
        if workers_type == ClusterHosts.Type.VIRTUAL:
            cloud_init_data["runcmd"] = [
                "sh -c \"echo $'default-lease-time 3600;\\nmax-lease-time 7200;"
                f"\\nauthoritative;\\nsubnet {rhel7_psi_network_config['subnet']} "
                "netmask 255.255.255.0 {"
                "\\noption subnet-mask 255.255.255.0;\\nrange  "
                f"{rhel7_psi_network_config['vm_address']} {rhel7_psi_network_config['vm_address']};"
                f"\\noption routers {rhel7_psi_network_config['default_gw']};\\n"
                f"option domain-name-servers {rhel7_psi_network_config['dns_server']};"
                "\\n}' > /etc/dhcp/dhcpd.conf\"",
                "sysctl net.ipv4.icmp_echo_ignore_broadcasts=0",
                "sudo systemctl enable dhcpd",
                "sudo systemctl restart dhcpd",
            ]

        with VirtualMachineForTests(
            namespace=namespace.name,
            name=name,
            body=fedora_vm_body(name=name),
            networks=networks,
            interfaces=sorted(networks.keys()),
            node_selector=worker_node1.name,
            cloud_init_data=cloud_init_data,
            client=unprivileged_client,
        ) as vm:
            vm.start(wait=True)
            wait_for_vm_interfaces(vmi=vm.vmi)
            enable_ssh_service_in_vm(vm=vm, console_impl=console.Fedora)
            yield vm
    else:
        yield


"""
VM creation from template
"""


@contextmanager
def vm_instance_from_template(
    request,
    unprivileged_client,
    namespace,
    data_volume,
    network_configuration,
    cloud_init_data,
    node_selector=None,
):
    """ Create a VM from template and start it (start step could be skipped by setting
    request.param['start_vm'] to False.

    The call to this function is triggered by calling either
    vm_instance_from_template_scope_function or vm_instance_from_template_scope_class.

    Prerequisite - a DV must be created prior to VM creation.
    """
    params = request.param if hasattr(request, "param") else request
    with VirtualMachineForTestsFromTemplate(
        name=params["vm_name"].replace(".", "-").lower(),
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**params["template_labels"]),
        template_dv=data_volume,
        vm_dict=params.get("vm_dict"),
        cpu_threads=params.get("cpu_threads"),
        memory=params.get("memory"),
        network_model=params.get("network_model"),
        network_multiqueue=params.get("network_multiqueue"),
        networks=network_configuration if network_configuration else None,
        interfaces=sorted(network_configuration.keys())
        if network_configuration
        else None,
        cloud_init_data=cloud_init_data if cloud_init_data else None,
        attached_secret=params.get("attached_secret"),
        node_selector=node_selector,
    ) as vm:
        if params.get("start_vm", True):
            vm.start(wait=True)
            vm.vmi.wait_until_running()
            if params.get("guest_agent", True):
                wait_for_vm_interfaces(vmi=vm.vmi)
        yield vm


@pytest.fixture()
def vm_instance_from_template_scope_function(
    request,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    network_configuration,
    cloud_init_data,
):
    """ Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=data_volume_multi_storage_scope_function,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def vm_instance_from_template_scope_class(
    request,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_class,
    network_configuration,
    cloud_init_data,
):
    """ Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=data_volume_multi_storage_scope_class,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
    ) as vm:
        yield vm


"""
Windows-specific fixtures
"""


@pytest.fixture(scope="module")
def sa_ready(namespace):
    #  Wait for 'default' service account secrets to be exists.
    #  The Pod creating will fail if we try to create it before.
    default_sa = ServiceAccount(name="default", namespace=namespace.name)
    sampler = TimeoutSampler(
        timeout=10, sleep=1, func=lambda: default_sa.instance.secrets
    )
    for sample in sampler:
        if sample:
            return


def winrmcli_pod(namespace):
    """ Deploy winrm-cli Pod into the same namespace.

    The call to this function is triggered by calling either
    winrmcli_pod_scope_module or winrmcli_pod_scope_class.
    """

    with WinRMcliPod(name="winrmcli-pod", namespace=namespace.name) as pod:
        pod.wait_for_status(status=pod.Status.RUNNING, timeout=90)
        yield pod


@pytest.fixture()
def winrmcli_pod_scope_function(rhel7_workers, namespace, sa_ready):
    # For RHEL7 workers, helper_vm is used
    if rhel7_workers:
        yield
    else:
        yield from winrmcli_pod(namespace=namespace)


@pytest.fixture(scope="module")
def winrmcli_pod_scope_module(rhel7_workers, namespace, sa_ready):
    # For RHEL7 workers, helper_vm is used
    if rhel7_workers:
        yield
    else:
        yield from winrmcli_pod(namespace=namespace)


@pytest.fixture(scope="class")
def winrmcli_pod_scope_class(rhel7_workers, namespace, sa_ready):
    # For RHEL7 workers, helper_vm is used
    if rhel7_workers:
        yield
    else:
        yield from winrmcli_pod(namespace=namespace)


@pytest.fixture()
def started_windows_vm(
    request,
    vm_instance_from_template_scope_function,
    winrmcli_pod_scope_function,
    bridge_attached_helper_vm,
):
    wait_for_windows_vm(
        vm=vm_instance_from_template_scope_function,
        version=request.param["os_version"],
        winrmcli_pod=winrmcli_pod_scope_function,
        timeout=1800,
        helper_vm=bridge_attached_helper_vm,
    )


def is_openshift(client):
    namespaces = [ns.name for ns in Namespace.get(client)]
    return "openshift-operators" in namespaces


@pytest.fixture(scope="session")
def skip_not_openshift(default_client):
    """
    Skip test if tests run on kubernetes (and not openshift)
    """
    if not is_openshift(default_client):
        pytest.skip("Skipping test requiring OpenShift")


@pytest.fixture(scope="session")
def worker_nodes_ipv4_false_secondary_nics(
    nodes_active_nics, schedulable_nodes, utility_pods
):
    """
    Function removes ipv4 from secondary nics.
    """
    for worker_node in schedulable_nodes:
        worker_nics = nodes_active_nics[worker_node.name]
        with EthernetNetworkConfigurationPolicy(
            name=f"disable-ipv4-{worker_node.name}",
            node_selector=worker_node.name,
            ipv4_dhcp=False,
            worker_pods=utility_pods,
            interfaces_name=worker_nics[1:],
            node_active_nics=worker_nics,
        ):
            LOGGER.info(
                f"selected worker node - {worker_node.name} under NNCP selected NIC information - {worker_nics} "
            )


@pytest.fixture(scope="session")
def cnv_current_version(default_client):
    for csv in ClusterServiceVersion.get(
        dyn_client=default_client, namespace=py_config["hco_namespace"]
    ):
        return csv.instance.spec.version


@pytest.fixture(scope="module")
def kubevirt_config_cm():
    return ConfigMap(name="kubevirt-config", namespace=py_config["hco_namespace"])


@pytest.fixture(scope="module")
def hco_namespace(default_client):
    return list(
        Namespace.get(
            dyn_client=default_client,
            field_selector=f"metadata.name=={py_config['hco_namespace']}",
        )
    )[0]


@pytest.fixture(scope="session")
def worker_node1(schedulable_nodes):
    # Get first worker nodes out of schedulable_nodes list
    return schedulable_nodes[0]


@pytest.fixture(scope="session")
def worker_node2(schedulable_nodes):
    # Get second worker nodes out of schedulable_nodes list
    return schedulable_nodes[1]


@pytest.fixture(scope="session")
def sriov_workers(schedulable_nodes):
    sriov_worker_label = "feature.node.kubernetes.io/network-sriov.capable"
    yield [
        node
        for node in schedulable_nodes
        if node.labels.get(sriov_worker_label) == "true"
    ]


@pytest.fixture(scope="session")
def skip_if_no_sriov_workers(sriov_workers):
    if not any(sriov_workers):
        pytest.skip(msg="Test should run on cluster with hosts that have SR-IOV card")


@pytest.fixture(scope="session")
def sriov_node_state(sriov_workers):
    return SriovNetworkNodeState(
        name=sriov_workers[0].name, policy_namespace=py_config["sriov_namespace"],
    )


@pytest.fixture(scope="session")
def sriov_node_policy(sriov_node_state):
    sriov_iface = sriov_node_state.instance.spec.interfaces[0]
    with SriovNetworkNodePolicy(
        name="test-sriov-policy",
        policy_namespace=sriov_node_state.namespace,
        pf_names=sriov_iface.name,
        root_devices=sriov_iface.pciAddress,
        num_vfs=sriov_iface.numVfs,
        resource_name=sriov_iface.vfGroups[0].resourceName,
    ) as policy:
        yield policy


@pytest.fixture(scope="session")
def bugzilla_connection_params(pytestconfig):
    bz_cfg = os.path.join(pytestconfig.rootdir, "bugzilla.cfg")
    parser = ConfigParser()
    # Open the file with the correct encoding
    parser.read(bz_cfg, encoding="utf-8")
    params_dict = {}
    for params in parser.items("DEFAULT"):
        params_dict[params[0]] = params[1]
    return params_dict


@pytest.fixture(scope="module")
def kubemacpool_range(hco_namespace):
    default_pool = ConfigMap(
        namespace=hco_namespace.name, name="kubemacpool-mac-range-config"
    )
    return default_pool.instance["data"]
