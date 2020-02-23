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
import urllib.request
from subprocess import PIPE, CalledProcessError, Popen, check_output

import bcrypt
import kubernetes
import pytest
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config
from resources.daemonset import DaemonSet
from resources.datavolume import DataVolume
from resources.network_attachment_definition import NetworkAttachmentDefinition
from resources.node import Node
from resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from resources.node_network_state import NodeNetworkState
from resources.oauth import OAuth
from resources.persistent_volume import PersistentVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.pod import Pod
from resources.secret import Secret
from resources.utils import TimeoutExpiredError, TimeoutSampler
from resources.virtual_machine import (
    VirtualMachine,
    VirtualMachineInstance,
    VirtualMachineInstanceMigration,
)
from utilities.infra import create_ns, generate_yaml_from_template
from utilities.storage import data_volume
from utilities.virt import kubernetes_taint_exists


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


def _get_client():
    return DynamicClient(kubernetes.config.new_client_from_config())


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
        if [
            fixture_name
            for fixture_name in item.fixturenames
            if "_matrix" in fixture_name
        ]:
            values = re.findall("(<.*?>)", item.name)
            for value in values:
                value = value.strip("<").strip(">")
                for k, v in py_config.items():
                    if isinstance(v, list):
                        if value in v:
                            item.user_properties.append(
                                (f"polarion-parameter-{k}", value)
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
    matrix_list = [
        fixture_name
        for fixture_name in metafunc.fixturenames
        if "_matrix" in fixture_name
    ]
    for matrix in matrix_list:
        _matrix_params = py_config[matrix]
        matrix_params = (
            _matrix_params if isinstance(_matrix_params, list) else [_matrix_params]
        )
        metafunc.parametrize(
            matrix,
            matrix_params,
            ids=[f"<{matrix_param}>" for matrix_param in matrix_params],
            scope="class",
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
    if session.config.getoption("storage_class_matrix"):
        # Extract only the dict item which has the requested key from
        # --storage-class-matrix
        py_config["storage_class_matrix"] = {
            k: v
            for i in py_config["storage_class_matrix"]
            for k, v in i.items()
            if k == session.config.getoption("storage_class_matrix")
        }


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
    except Exception as exception_:
        LOGGER.warning(f"Collecting 'failed tests log' failed {exception_} ")


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
    login_command = f"oc login {api_address} -u {user}"
    if password:
        login_command += f" -p {password}"
    samples = TimeoutSampler(
        timeout=120,
        sleep=3,
        exceptions=CalledProcessError,
        func=Popen,
        args=login_command,
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
    )
    for sample in samples:
        LOGGER.info(
            f"Trying to login to {user} user shell. Login command: {login_command}"
        )
        login_result = sample.communicate()
        if sample.returncode == 0:
            LOGGER.info(f"Login to {user} user shell - success")
            return
        LOGGER.warning(
            f"Login to unprivileged user - warning due to the following error: {login_result[0]}"
        )


@pytest.fixture(scope="session", autouse=True)
def junitxml_polarion(request):
    """
    Add polarion needed attributes to junit xml

    export as os environment:
        POLARION_CUSTOM_PLANNEDIN
        POLARION_TESTRUN_ID
    """
    if request.config.pluginmanager.hasplugin("junitxml"):
        my_junit = getattr(request.config, "_xml", None)
        if my_junit:
            my_junit.add_global_property("polarion-custom-isautomated", "True")
            my_junit.add_global_property("polarion-testrun-status-id", "inprogress")
            my_junit.add_global_property(
                "polarion-custom-plannedin", os.getenv("POLARION_CUSTOM_PLANNEDIN")
            )
            my_junit.add_global_property("polarion-user-id", "cnvqe")
            my_junit.add_global_property("polarion-project-id", "CNV")
            my_junit.add_global_property("polarion-response-myproduct", "cnv-test-run")
            my_junit.add_global_property(
                "polarion-testrun-id", os.getenv("POLARION_TESTRUN_ID")
            )


@pytest.fixture(scope="session", autouse=True)
def default_client():
    """
    Get DynamicClient
    """
    return _get_client()


@pytest.fixture(scope="session")
def unprivileged_secret(default_client):
    if py_config["distribution"] == "upstream":
        yield

    else:
        password = UNPRIVILEGED_PASSWORD.encode()
        enc_password = bcrypt.hashpw(password, bcrypt.gensalt(5, prefix=b"2a")).decode()
        crypto_credentials = f"{UNPRIVILEGED_USER}:{enc_password}".encode()
        with Secret(
            name="htpass-secret",
            namespace="openshift-config",
            htpasswd=base64.b64encode(crypto_credentials).decode(),
        ):
            yield


@pytest.fixture(scope="session", autouse=True)
def unprivileged_client(default_client, unprivileged_secret):
    """
    Provides none privilege API client
    """
    # To disable unprivileged_client pass --tc=no_unprivileged_client:True to pytest commandline.

    if py_config["distribution"] == "upstream" or py_config.get(
        "no_unprivileged_client"
    ):
        return

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
    try:
        login_to_account(
            api_address=default_client.configuration.host,
            user=UNPRIVILEGED_USER,
            password=UNPRIVILEGED_PASSWORD,
        )  # Login to unprivileged account
    except TimeoutExpiredError:
        return

    token = check_output("oc whoami -t", shell=True).decode().strip()  # Get token
    login_to_account(
        api_address=default_client.configuration.host, user=current_user.strip()
    )  # Get back to admin account
    token_auth = {
        "api_key": {"authorization": f"Bearer {token}"},
        "host": default_client.configuration.host,
        "verify_ssl": True,
        "ssl_ca_cert": default_client.configuration.ssl_ca_cert,
    }
    configuration = kubernetes.client.Configuration()
    for k, v in token_auth.items():
        setattr(configuration, k, v)
    k8s_client = kubernetes.client.ApiClient(configuration)
    return DynamicClient(k8s_client)


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
    ]


@pytest.fixture(scope="session")
def masters(nodes):
    yield [
        node for node in nodes if "node-role.kubernetes.io/master" in node.labels.keys()
    ]


@pytest.fixture(scope="session")
def net_utility_daemonset(default_client):
    """
    Deploy network utility daemonset into the kube-system namespace.

    This daemonset deploys a pod on every node with hostNetwork and the main usage is to run commands on the hosts.
    For example to create linux bridge and other components related to the host configuration.
    """
    with NetUtilityDaemonSet(name="net-utility", namespace="kube-system") as ds:
        ds.wait_until_deployed()
        yield ds


@pytest.fixture(scope="session")
def network_utility_pods(schedulable_nodes, net_utility_daemonset, default_client):
    """
    Get network utility pods.
    When the tests start we deploy a pod on every host in the cluster using a daemonset.
    These pods have a label of cnv-test=net-utility and they are privileged pods with hostnetwork=true
    """
    # get only pods that running on schedulable_nodes.
    pods = list(Pod.get(default_client, label_selector="cnv-test=net-utility"))
    return [
        pod
        for pod in pods
        if pod.node.name in [node.name for node in schedulable_nodes]
    ]


@pytest.fixture(scope="session")
def nodes_active_nics(schedulable_nodes):
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


class NetUtilityDaemonSet(DaemonSet):
    def to_dict(self):
        res = super().to_dict()
        res.update(
            generate_yaml_from_template(
                file_=os.path.join(
                    os.path.dirname(__file__), "net-utility-daemonset.yaml"
                )
            )
        )
        return res


@pytest.fixture(scope="session")
def cnv_containers():
    res = {}
    if py_config["distribution"] == "upstream":
        return res

    data = urllib.request.urlopen(
        "http://download-node-02.eng.bos.redhat.com/rhel-8/nightly/CNV/latest-CNV-2.3-RHEL-8/containers.list",
        timeout=60,
    )
    if data.getcode() != 200:
        return res

    for line in data.readlines():
        line = line.decode("utf-8")
        if "image:" in line:
            line = line.strip()
            image_url = line.rsplit()[-1].strip()
            image_url = image_url.strip('"')
            name = image_url.rsplit("/", 1)[-1].split(":")[0]
            res[name] = image_url

    return res


@pytest.fixture(scope="module")
def namespace(request, unprivileged_client):
    """ Generate namespace from the test's module name """
    name = (
        request.fspath.strpath.split(f"{os.path.dirname(__file__)}/")[1]
        .strip(".py")
        .replace("/", "-")
        .replace("_", "-")
    )[-63:]
    yield from create_ns(client=unprivileged_client, name=name.split("-", 1)[-1])


@pytest.fixture(scope="session")
def skip_upstream():
    if py_config["distribution"] == "upstream":
        pytest.skip(
            msg="Running only on downstream,"
            "Reason: HTTP/Registry servers are not available for upstream",
        )


@pytest.fixture(scope="session")
def skip_not_bare_metal():
    if not py_config["bare_metal_cluster"]:
        pytest.skip(msg="Test should run only BM",)


@pytest.fixture(scope="session", autouse=True)
def leftovers():
    secret = Secret(name="htpass-secret", namespace="openshift-config")
    ds = NetUtilityDaemonSet(name="net-utility", namespace="kube-system")
    for resource_ in (secret, ds):
        try:
            if resource_.instance:
                resource_.delete(wait=True)
        except NotFoundError:
            continue


# RHEL 7 specific fixtures
@pytest.fixture(scope="session")
def rhel7_workers(schedulable_nodes):
    # Check only the first Node since mixed rchos and RHEL7 workers in cluster is not supported.
    return re.search(
        r"^Red Hat Enterprise Linux Server 7\.\d",
        schedulable_nodes[0].instance.status.nodeInfo.osImage,
    )


@pytest.fixture(scope="session")
def skip_rhel7_workers(rhel7_workers):
    if rhel7_workers:
        pytest.skip(msg="Test should skip on RTHEL7 workers")


@pytest.fixture(scope="class")
def skip_ceph_on_rhel7(storage_class_matrix, rhel7_workers):
    if storage_class_matrix.get("rook-ceph-block"):
        if rhel7_workers:
            pytest.skip(
                msg="Rook-ceph configuration is not supported on RHEL7 workers",
            )


@pytest.fixture(scope="session")
def rhel7_ovs_bridge(rhel7_workers, network_utility_pods):
    if rhel7_workers:
        # All RHEL workers should be with the same configuration, gating info from the first worker.
        connections = network_utility_pods[0].execute(
            command=["nmcli", "-t", "connection", "show"]
        )
        for connection in connections.splitlines():
            if "ovs-bridge" in connection:
                return connection.split(":")[-1]


@pytest.fixture(scope="session")
def skip_no_rhel7_workers(rhel7_workers):
    if not rhel7_workers:
        pytest.skip(msg="Test should run only with cluster with RTHEL7 workers")


@pytest.fixture()
def data_volume_scope_function(
    request, skip_ceph_on_rhel7, namespace, storage_class_matrix, schedulable_nodes
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix,
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="class")
def data_volume_scope_class(
    request, skip_ceph_on_rhel7, namespace, storage_class_matrix, schedulable_nodes
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix,
        schedulable_nodes=schedulable_nodes,
    )
