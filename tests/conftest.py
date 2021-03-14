# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV tests
"""
import base64
import logging
import os
import os.path
import re
import shlex
import shutil
from collections import Counter
from contextlib import contextmanager
from subprocess import PIPE, CalledProcessError, Popen, check_output

import bcrypt
import kubernetes
import pytest
import rrmngmnt
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.configmap import ConfigMap
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.hostpath_provisioner import HostPathProvisioner
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.namespace import Namespace
from ocp_resources.network import Network
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.node import Node
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.oauth import OAuth
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.role_binding import RoleBinding
from ocp_resources.secret import Secret
from ocp_resources.service_account import ServiceAccount
from ocp_resources.sriov_network_node_state import SriovNetworkNodeState
from ocp_resources.storage_class import StorageClass
from ocp_resources.template import Template
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config

from utilities.constants import (
    RESOURCES_TO_COLLECT_INFO,
    SRIOV,
    TEST_COLLECT_INFO_DIR,
    TEST_LOG_FILE,
)
from utilities.hco import apply_np_changes
from utilities.infra import (
    BUG_STATUS_CLOSED,
    ClusterHosts,
    collect_logs_pods,
    collect_logs_resources,
    create_ns,
    generate_namespace_name,
    get_admin_client,
    get_bug_status,
    get_bugzilla_connection_params,
    get_schedulable_nodes_ips,
    prepare_test_dir_log,
    run_ssh_commands,
    separator,
    setup_logging,
)
from utilities.network import (
    OVS,
    EthernetNetworkConfigurationPolicy,
    MacPool,
    enable_hyperconverged_ovs_annotations,
    network_device,
    network_nad,
    wait_for_ovs_daemonset_resource,
    wait_for_ovs_status,
)
from utilities.storage import data_volume
from utilities.virt import (
    FEDORA_CLOUD_INIT_PASSWORD,
    RHEL_CLOUD_INIT_PASSWORD,
    VirtualMachineForTestsFromTemplate,
    generate_yaml_from_template,
    kubernetes_taint_exists,
    nmcli_add_con_cmds,
    running_vm,
    wait_for_windows_vm,
)


LOGGER = logging.getLogger(__name__)
BASIC_LOGGER = logging.getLogger("basic")
UNPRIVILEGED_USER = "unprivileged-user"
UNPRIVILEGED_PASSWORD = "unprivileged-password"
HTTP_SECRET_NAME = "htpass-secret-for-cnv-tests"
OPENSHIFT_CONFIG_NAMESPACE = "openshift-config"
HTPASSWD_PROVIDER_DICT = {
    "name": "htpasswd_provider",
    "mappingMethod": "claim",
    "type": "HTPasswd",
    "htpasswd": {"fileData": {"name": HTTP_SECRET_NAME}},
}
ACCESS_TOKEN = {"accessTokenMaxAgeSeconds": 604800}

TESTS_MARKERS = ["destructive", "chaos", "tier3"]

TEAM_MARKERS = {
    "ansible": ["ansible-module"],
    "compute": ["compute", "metrics"],
    "network": ["network"],
    "storage": ["storage"],
    "mtv": ["mtv"],
    "iuo": ["csv", "install_upgrade_operators", "security", "must_gather"],
}


def pytest_addoption(parser):
    matrix_group = parser.getgroup(name="Matrix")
    upgrade_group = parser.getgroup(name="Upgrade")
    workers_group = parser.getgroup(name="Workers")
    storage_group = parser.getgroup(name="Storage")

    # Upgrade addoption
    upgrade_group.addoption(
        "--upgrade", choices=["cnv", "ocp"], help="Run OCP or CNV upgrade tests"
    )
    upgrade_group.addoption("--cnv-version", help="CNV version to upgrade to")
    upgrade_group.addoption("--ocp-image", help="OCP image to upgrade to")
    upgrade_group.addoption(
        "--upgrade_resilience",
        action="store_true",
        help="If provided, run upgrade with disruptions",
    )

    # Matrix addoption
    matrix_group.addoption("--storage-class-matrix", help="Storage class matrix to use")
    matrix_group.addoption("--bridge-device-matrix", help="Bridge device matrix to use")
    matrix_group.addoption("--rhel-os-matrix", help="RHEL OS matrix to use")
    matrix_group.addoption("--windows-os-matrix", help="Windows OS matrix to use")
    matrix_group.addoption("--fedora-os-matrix", help="Fedora OS matrix to use")
    matrix_group.addoption("--centos-os-matrix", help="CentOS matrix to use")
    matrix_group.addoption("--provider-matrix", help="External provider matrix to use")
    matrix_group.addoption("--vm-volumes-matrix", help="VM volumes matrix to use")
    matrix_group.addoption("--run-strategy-matrix", help="RunStrategy matrix to use")

    # Workers addoption
    workers_group.addoption(
        "--rhel7-workers",
        help="If running on cluster with RHEL7 workers",
        action="store_true",
    )

    # Storage addoption
    storage_group.addoption(
        "--default-storage-class",
        help="Overwrite default storage class in storage_class_matrix",
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

        # Add tier3 marker for Windows matrix tests running with sc that is not OCS
        add_tier3_marker = []
        for user_property in item.user_properties:
            if "polarion-parameter-windows_os_matrix" in user_property or (
                "polarion-parameter-storage_class_matrix" in user_property
                and "ocs-storagecluster-ceph-rbd" not in user_property
            ):
                add_tier3_marker.append(True)
            if len(add_tier3_marker) == 2:
                item.add_marker(marker="tier3")

        # Add tier2 marker for tests without any marker.
        markers = [mark.name for mark in list(item.iter_markers())]
        if not [mark for mark in markers if mark in TESTS_MARKERS]:
            item.add_marker(marker="tier2")

        # Mark tests by team.
        def _mark_tests_by_team(_item):
            for team, vals in TEAM_MARKERS.items():
                if _item.location[0].split("/")[1] in vals:
                    _item.add_marker(marker=team)

        _mark_tests_by_team(_item=item)

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


def pytest_report_teststatus(report, config):
    test_name = report.head_line
    when = report.when
    call_str = "call"
    if report.passed:
        if when == call_str:
            BASIC_LOGGER.info(f"\nTEST: {test_name} STATUS: \033[0;32mPASSED\033[0m")

    elif report.skipped:
        BASIC_LOGGER.info(f"\nTEST: {test_name} STATUS: \033[1;33mSKIPPED\033[0m")

    elif report.failed:
        if when != call_str:
            BASIC_LOGGER.info(
                f"\nTEST: {test_name} STATUS: [{when}] \033[0;31mERROR\033[0m"
            )
        else:
            BASIC_LOGGER.info(f"\nTEST: {test_name} STATUS: \033[0;31mFAILED\033[0m")


def pytest_runtest_makereport(item, call):
    """
    incremental tests implementation
    """
    if call.excinfo is not None and "incremental" in item.keywords:
        parent = item.parent
        parent._previousfailed = item


def pytest_runtest_setup(item):
    """
    Use incremental
    """
    BASIC_LOGGER.info(f"{separator(symbol_='-', val=item.name)}")
    BASIC_LOGGER.info(f"{separator(symbol_='-', val='SETUP')}")
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail("previous test failed (%s)" % previousfailed.name)

    prepare_test_dir_log(item=item, prefix="setup")


def pytest_runtest_call(item):
    BASIC_LOGGER.info(f"{separator(symbol_='-', val='CALL')}")
    prepare_test_dir_log(item=item, prefix="call")


def pytest_runtest_teardown(item):
    BASIC_LOGGER.info(f"{separator(symbol_='-', val='TEARDOWN')}")
    prepare_test_dir_log(item=item, prefix="teardown")


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
            fixture_name,
            matrix_params,
            ids=ids,
            scope=scope[0],
        )


def pytest_sessionstart(session):
    if os.path.exists(TEST_LOG_FILE):
        os.remove(TEST_LOG_FILE)

    setup_logging(log_file=TEST_LOG_FILE)
    py_config_scs = py_config.get("storage_class_matrix", {})
    # Only HPP storage is supported when running with RHEL7 workers.
    if session.config.getoption("rhel7_workers"):
        py_config_scs = [
            sc for sc in py_config_scs if [*sc][0] == "hostpath-provisioner"
        ]

    # Save the default storage_class_matrix before it is updated
    # with runtime storage_class_matrix value(s)
    py_config["system_storage_class_matrix"] = py_config_scs

    # Save the default windows_os_matrix before it is updated
    # with runtime windows_os_matrix value(s).
    # Some tests extract a single OS from the matrix and may fail if running with
    # passed values from cli
    py_config["system_windows_os_matrix"] = py_config["windows_os_matrix"]

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
                    if item == val:
                        items_list.append(item)

        py_config[key] = items_list

    config_default_storage_class(session=session)


def pytest_sessionfinish(session, exitstatus):
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    deselected_str = "deselected"
    deselected = len(reporter.stats.get(deselected_str, []))
    summary = (
        f"{deselected} {deselected_str}, "
        f"{reporter.pass_count} {'passed'}, "
        f"{reporter.skip_count} {'skipped'}, "
        f"{reporter.fail_count} {'failed'}, "
        f"{reporter.error_count} {'error'} "
        f"{reporter.xfail_count} {'xfail'} "
        f"{reporter.xpass_count} {'xpass'} "
    )
    BASIC_LOGGER.info(f"{separator(symbol_='-', val=summary)}")


def pytest_exception_interact(node, call, report):
    BASIC_LOGGER.error(report.longreprtext)

    if os.environ.get("CNV_TEST_COLLECT_LOGS", "0") != "0":
        try:
            namespace_name = generate_namespace_name(
                file_path=node.fspath.strpath.split(f"{os.path.dirname(__file__)}/")[1]
            )
            dyn_client = get_admin_client()
            collect_logs_resources(
                namespace_name=namespace_name,
                resources_to_collect=RESOURCES_TO_COLLECT_INFO,
            )
            pods = list(Pod.get(dyn_client=dyn_client))
            collect_logs_pods(pods=pods)

        except Exception as exp:
            LOGGER.debug(f"Failed to collect logs: {exp}")
            return


@pytest.fixture(scope="session", autouse=True)
def tests_collect_info_dir():
    shutil.rmtree(TEST_COLLECT_INFO_DIR, ignore_errors=True)


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
        wait_timeout=60,
        sleep=3,
        exceptions=CalledProcessError,
        func=Popen,
        args=login_command,
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
    )
    login_result = None
    try:
        LOGGER.info(
            f"Trying to login to {user} user shell. Login command: {login_command}"
        )
        for sample in samples:
            login_result = sample.communicate()
            if sample.returncode == 0:
                LOGGER.info(f"Login to {user} user shell - success")
                return True

            if [err for err in stop_errors if err in login_result[1].decode("utf-8")]:
                break

    except TimeoutExpiredError:
        if login_result:
            LOGGER.warning(
                f"Login to unprivileged user - failed due to the following error: "
                f"{login_result[0].decode('utf-8')} {login_result[1].decode('utf-8')}"
            )
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
def admin_client():
    """
    Get DynamicClient
    """
    return get_admin_client()


@pytest.fixture(scope="session")
def unprivileged_secret(admin_client):
    if py_config["distribution"] == "upstream" or py_config.get(
        "no_unprivileged_client"
    ):
        yield

    else:
        password = UNPRIVILEGED_PASSWORD.encode()
        enc_password = bcrypt.hashpw(password, bcrypt.gensalt(5, prefix=b"2a")).decode()
        crypto_credentials = f"{UNPRIVILEGED_USER}:{enc_password}".encode()
        with Secret(
            name=HTTP_SECRET_NAME,
            namespace=OPENSHIFT_CONFIG_NAMESPACE,
            htpasswd=base64.b64encode(crypto_credentials).decode(),
        ) as secret:
            yield secret

        #  Wait for oauth-openshift deployment to update after removing htpass-secret
        _wait_for_oauth_openshift_deployment(admin_client=admin_client)


def _wait_for_oauth_openshift_deployment(admin_client):
    dp = next(
        Deployment.get(
            dyn_client=admin_client,
            name="oauth-openshift",
            namespace="openshift-authentication",
        )
    )
    _log = f"Wait for {dp.name} -> Type: Progressing -> Reason:"

    def _wait_sampler(reason):
        sampler = TimeoutSampler(
            wait_timeout=60, sleep=1, func=lambda: dp.instance.status.conditions
        )
        for sample in sampler:
            for _spl in sample:
                if _spl.type == "Progressing" and _spl.reason == reason:
                    return

    for reason in ("ReplicaSetUpdated", "NewReplicaSetAvailable"):
        LOGGER.info(f"{_log} {reason}")
        _wait_sampler(reason=reason)


@pytest.fixture(scope="session")
def identity_provider_config():
    return OAuth(name="cluster")


@pytest.fixture(scope="session")
def unprivileged_client(admin_client, unprivileged_secret, identity_provider_config):
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
        identity_provider_config_editor = ResourceEditor(
            patches={
                identity_provider_config: {
                    "metadata": {"name": identity_provider_config.name},
                    "spec": {
                        "identityProviders": [HTPASSWD_PROVIDER_DICT],
                        "tokenConfig": ACCESS_TOKEN,
                    },
                }
            }
        )
        identity_provider_config_editor.update(backup_resources=True)
        _wait_for_oauth_openshift_deployment(admin_client=admin_client)

        current_user = (
            check_output("oc whoami", shell=True).decode().strip()
        )  # Get current admin account
        if kube_config_exists:
            os.environ["KUBECONFIG"] = ""

        if login_to_account(
            api_address=admin_client.configuration.host,
            user=UNPRIVILEGED_USER,
            password=UNPRIVILEGED_PASSWORD,
        ):  # Login to unprivileged account
            token = (
                check_output("oc whoami -t", shell=True).decode().strip()
            )  # Get token
            token_auth = {
                "api_key": {"authorization": f"Bearer {token}"},
                "host": admin_client.configuration.host,
                "verify_ssl": True,
                "ssl_ca_cert": admin_client.configuration.ssl_ca_cert,
            }
            configuration = kubernetes.client.Configuration()
            for k, v in token_auth.items():
                setattr(configuration, k, v)

            if kubeconfig_env:
                os.environ["KUBECONFIG"] = kubeconfig_env

            login_to_account(
                api_address=admin_client.configuration.host, user=current_user.strip()
            )  # Get back to admin account

            k8s_client = kubernetes.client.ApiClient(configuration)
            yield DynamicClient(k8s_client)
        else:
            yield

        # Teardown
        if identity_provider_config_editor:
            identity_provider_config_editor.restore()

        if token:
            try:
                if kube_config_exists:
                    os.environ["KUBECONFIG"] = ""

                login_to_account(
                    api_address=admin_client.configuration.host,
                    user=UNPRIVILEGED_USER,
                    password=UNPRIVILEGED_PASSWORD,
                )  # Login to unprivileged account
                LOGGER.info("Logout unprivileged_client")
                Popen(args=["oc", "logout"], stdout=PIPE, stderr=PIPE).communicate()
            finally:
                if kubeconfig_env:
                    os.environ["KUBECONFIG"] = kubeconfig_env

                login_to_account(
                    api_address=admin_client.configuration.host,
                    user=current_user.strip(),
                )  # Get back to admin account


@pytest.fixture(scope="session")
def schedulable_node_ips(schedulable_nodes):
    """
    Store all kubevirt.io/schedulable=true IPs
    """
    return get_schedulable_nodes_ips(nodes=schedulable_nodes)


@pytest.fixture(scope="session")
def skip_when_one_node(schedulable_nodes):
    if len(schedulable_nodes) < 2:
        pytest.skip(msg="Test requires at least 2 nodes")


@pytest.fixture(scope="session")
def nodes(admin_client):
    yield list(Node.get(dyn_client=admin_client))


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
def utility_daemonset(admin_client):
    """
    Deploy utility daemonset into the kube-system namespace.

    This daemonset deploys a pod on every node with hostNetwork and the main usage is to run commands on the hosts.
    For example to create linux bridge and other components related to the host configuration.
    """
    with UtilityDaemonSet(name="utility", namespace="kube-system") as ds:
        ds.wait_until_deployed()
        yield ds


@pytest.fixture(scope="session")
def utility_pods(schedulable_nodes, utility_daemonset, admin_client):
    """
    Get utility pods.
    When the tests start we deploy a pod on every host in the cluster using a daemonset.
    These pods have a label of cnv-test=utility and they are privileged pods with hostnetwork=true
    """
    # get only pods that running on schedulable_nodes.
    pods = list(Pod.get(admin_client, label_selector="cnv-test=utility"))
    missing_pods = [
        node.name
        for node in schedulable_nodes
        if node.name not in [pod.node.name for pod in pods]
    ]
    assert not missing_pods, f"Missing utility pod for: {' '.join(missing_pods)}"
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
        host.executor_user = host_user
        host.add_user(user=host_user)
        executors[pod.node.name] = host

    return executors


@pytest.fixture(scope="session")
def node_physical_nics(admin_client, utility_pods, workers_ssh_executors):
    if is_openshift(admin_client):
        return {
            node: workers_ssh_executors[node].network.all_interfaces()
            for node in workers_ssh_executors.keys()
        }
    else:
        return network_interfaces_k8s(utility_pods=utility_pods)


def network_interfaces_k8s(utility_pods):
    interfaces = {}
    for pod in utility_pods:
        node = pod.instance.spec.nodeName
        output = pod.execute(
            ["bash", "-c", "ls -la /sys/class/net | grep pci | grep -o '[^/]*$'"]
        ).split("\n")
        interfaces[node] = list(filter(None, output))  # Filter out empty lines

    return interfaces


@pytest.fixture(scope="session")
def ovn_kubernetes_cluster(admin_client):
    cluster_network = list(Network.get(dyn_client=admin_client))[0]
    return cluster_network.instance.status.networkType == "OVNKubernetes"


# TODO: Remove this fixture and its usage in nodes_active_nics when BZ 1885605 is fixed.
@pytest.fixture(scope="session")
def ovs_bridge_bug_closed(bugzilla_connection_params):
    return (
        get_bug_status(
            bugzilla_connection_params=bugzilla_connection_params, bug=1885605
        )
        in BUG_STATUS_CLOSED
    )


@pytest.fixture(scope="session")
def nodes_active_nics(
    schedulable_nodes,
    node_physical_nics,
    ovn_kubernetes_cluster,
    ovs_bridge_bug_closed,
    workers_ssh_executors,
):
    # TODO: Remove this function and its usage in nodes_active_nics when BZ 1885605 is fixed.
    def _ovs_bridge_ports(node_interface):
        ports = set()
        if ovs_bridge_bug_closed or not ovn_kubernetes_cluster:
            return ports

        if node_interface.type == "ovs-bridge" and node_interface.bridge.port:
            for bridge_port in node_interface.bridge.port:
                ports.add(bridge_port.name)
        return ports

    """
    Get nodes active NICs.
    First NIC is management NIC
    """
    nodes_nics = {}
    for node in schedulable_nodes:
        nodes_nics[node.name] = {"available": [], "occupied": []}
        nns = NodeNetworkState(name=node.name)
        host = workers_ssh_executors[node.name]

        #  Use one ssh connection to the node.
        with host.executor().session() as ssh_session:
            for node_iface in nns.interfaces:

                #  Exclude SR-IOV (VFs) interfaces.
                if re.findall(r"v\d+$", node_iface.name):
                    continue

                if node_iface.name in nodes_nics[node.name]["occupied"]:
                    continue

                # BZ 1885605 workaround: If any of the node's physical interfaces serves as a port of an
                # OVS bridge, it shouldn't be used for tests' node networking.
                bridge_ports = _ovs_bridge_ports(node_interface=node_iface)
                for port in bridge_ports:
                    if port in node_physical_nics[node.name]:
                        nodes_nics[node.name]["occupied"].append(port)
                        if port in nodes_nics[node.name]["available"]:
                            nodes_nics[node.name]["available"].remove(port)

                if node_iface.name not in node_physical_nics[node.name]:
                    continue

                ethtool_state = ssh_session.run_cmd(
                    cmd=shlex.split(f"ethtool {node_iface.name}")
                )[1]
                if "Link detected: no" in ethtool_state:
                    continue

                if node_iface["ipv4"]["address"] and node_iface["ipv4"]["dhcp"]:
                    nodes_nics[node.name]["occupied"].append(node_iface.name)
                else:
                    nodes_nics[node.name]["available"].append(node_iface.name)

    return nodes_nics


@pytest.fixture(scope="session")
def nodes_available_nics(nodes_active_nics):
    return {
        node: nodes_active_nics[node]["available"] for node in nodes_active_nics.keys()
    }


@pytest.fixture(scope="session")
def nodes_occupied_nics(nodes_active_nics):
    return {
        node: nodes_active_nics[node]["occupied"] for node in nodes_active_nics.keys()
    }


@pytest.fixture(scope="session")
def multi_nics_nodes(hosts_common_available_ports):
    """
    Check if nodes has any available NICs
    """
    return bool(hosts_common_available_ports)


@pytest.fixture(scope="session")
def skip_if_no_multinic_nodes(multi_nics_nodes):
    if not multi_nics_nodes:
        pytest.skip("Only run on multi NICs node")


class UtilityDaemonSet(DaemonSet):
    def to_dict(self):
        from pkg_resources import resource_stream

        yaml_file = resource_stream(
            "utilities", "manifests/utility-daemonset.yaml"
        ).name
        res = super().to_dict()
        res.update(generate_yaml_from_template(file_=yaml_file))
        return res


@pytest.fixture(scope="module")
def namespace(request, unprivileged_client):
    """ Generate namespace from the test's module name """
    client = True
    if hasattr(request, "param"):
        client = request.param.get("unprivileged_client", True)

    yield from create_ns(
        client=unprivileged_client if client else None,
        name=generate_namespace_name(
            file_path=request.fspath.strpath.split(f"{os.path.dirname(__file__)}/")[1]
        ),
    )


@pytest.fixture(scope="session")
def skip_upstream():
    if py_config["distribution"] == "upstream":
        pytest.skip(
            msg="Running only on downstream,"
            "Reason: HTTP/Registry servers are not available for upstream",
        )


@pytest.fixture(scope="session", autouse=True)
def leftovers(identity_provider_config):
    secret = Secret(name=HTTP_SECRET_NAME, namespace=OPENSHIFT_CONFIG_NAMESPACE)
    ds = UtilityDaemonSet(name="utility", namespace="kube-system")
    #  Delete Secret and DaemonSet created by us.
    for resource_ in (secret, ds):
        try:
            if resource_.instance:
                resource_.delete(wait=True)
        except NotFoundError:
            continue

    #  Remove leftovers from OAuth
    identity_providers_spec = identity_provider_config.instance.to_dict()["spec"]
    identity_providers_token = identity_providers_spec.get("tokenConfig")
    identity_providers = identity_providers_spec.get("identityProviders", [])

    if ACCESS_TOKEN == identity_providers_token:
        identity_providers_spec["tokenConfig"] = None

    if HTPASSWD_PROVIDER_DICT in identity_providers:
        identity_providers.pop(identity_providers.index(HTPASSWD_PROVIDER_DICT))
        identity_providers_spec["identityProviders"] = identity_providers or None

    r_editor = ResourceEditor(
        patches={
            identity_provider_config: {
                "metadata": {"name": identity_provider_config.name},
                "spec": identity_providers_spec,
            }
        }
    )
    r_editor.update()


@pytest.fixture(scope="session")
def workers_type(workers_ssh_executors):
    for _, exec in workers_ssh_executors.items():
        out = run_ssh_commands(
            host=exec,
            commands=[["bash", "-c", "dmesg | grep 'Hypervisor detected' | wc -l"]],
        )[0]

        if int(out) > 0:
            return ClusterHosts.Type.VIRTUAL

    return ClusterHosts.Type.PHYSICAL


@pytest.fixture(scope="module")
def skip_if_workers_vms(workers_type):
    if workers_type == ClusterHosts.Type.VIRTUAL:
        pytest.skip(msg="Test should run only BM cluster")


# RHEL 7 specific fixtures
@pytest.fixture(scope="session")
def rhel7_workers(pytestconfig):
    return pytestconfig.getoption("rhel7_workers")


@pytest.fixture(scope="session")
def skip_rhel7_workers(rhel7_workers):
    if rhel7_workers:
        pytest.skip(msg="Test should skip on RHEL7 workers")


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
def network_attachment_definition(rhel7_ovs_bridge, namespace, rhel7_workers):
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
    rhel7_workers,
    network_attachment_definition,
):
    if rhel7_workers:
        return {network_attachment_definition.name: network_attachment_definition.name}


@pytest.fixture()
def data_volume_multi_storage_scope_function(
    request,
    namespace,
    storage_class_matrix__function__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix__function__,
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="class")
def data_volume_multi_storage_scope_class(
    request,
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


@pytest.fixture(scope="class")
def golden_image_data_volume_multi_storage_scope_class(
    admin_client,
    request,
    golden_images_namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture()
def golden_image_data_volume_multi_storage_scope_function(
    admin_client,
    request,
    golden_images_namespace,
    storage_class_matrix__function__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__function__,
        schedulable_nodes=schedulable_nodes,
        check_dv_exists=True,
        admin_client=admin_client,
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
def golden_image_data_volume_scope_class(
    request, admin_client, golden_images_namespace, schedulable_nodes
):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class=request.param["storage_class"],
        schedulable_nodes=schedulable_nodes,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture()
def golden_image_data_volume_scope_function(
    request, admin_client, golden_images_namespace, schedulable_nodes
):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class=request.param["storage_class"],
        schedulable_nodes=schedulable_nodes,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def cloud_init_data(
    request,
    workers_type,
    rhel7_workers,
    rhel7_psi_network_config,
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
        cloud_init_data["userData"]["bootcmd"] = bootcmds

        return cloud_init_data


"""
VM creation from template
"""


@contextmanager
def vm_instance_from_template(
    request,
    unprivileged_client,
    namespace,
    rhel7_workers=False,
    data_volume=None,
    data_volume_template=None,
    existing_data_volume=None,
    network_configuration=None,
    cloud_init_data=None,
    node_selector=None,
    vm_cpu_model=None,
):
    """Create a VM from template and start it (start step could be skipped by setting
    request.param['start_vm'] to False.

    The call to this function is triggered by calling either
    vm_instance_from_template_multi_storage_scope_function or vm_instance_from_template_multi_storage_scope_class.

    Prerequisite - a DV must be created prior to VM creation.

    Args:
        data_volume (obj `DataVolume`: DV resource): existing DV that will be cloned (for example: golden image)
        data_volume_template (dict): dataVolumeTemplates dict; will replace dataVolumeTemplates in VM yaml
        existing_data_volume (obj `DataVolume`: DV resource): existing DV to be consumed directly (not cloned)

    Yields:
        obj `VirtualMachine`: VM resource

    """
    params = request.param if hasattr(request, "param") else request
    with VirtualMachineForTestsFromTemplate(
        name=params["vm_name"].replace(".", "-").lower(),
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**params["template_labels"]),
        data_volume=data_volume,
        data_volume_template=data_volume_template,
        existing_data_volume=existing_data_volume,
        vm_dict=params.get("vm_dict"),
        cpu_threads=params.get("cpu_threads"),
        memory_requests=params.get("memory_requests"),
        network_model=params.get("network_model"),
        network_multiqueue=params.get("network_multiqueue"),
        networks=network_configuration,
        interfaces=sorted(network_configuration.keys())
        if network_configuration
        else None,
        cloud_init_data=cloud_init_data,
        attached_secret=params.get("attached_secret"),
        node_selector=node_selector,
        diskless_vm=params.get("diskless_vm"),
        cpu_model=params.get("cpu_model") or vm_cpu_model,
        ssh=params.get("ssh", True),
        disk_options_vm=params.get("disk_io_option"),
        rhel7_workers=rhel7_workers,
    ) as vm:
        if params.get("start_vm", True):
            running_vm(
                vm=vm,
                wait_for_interfaces=params.get("guest_agent", True),
                enable_ssh=vm.ssh,
            )
        yield vm


@pytest.fixture()
def vm_instance_from_template_multi_storage_scope_function(
    request,
    rhel7_workers,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    network_configuration,
    cloud_init_data,
    nodes_common_cpu_model,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        rhel7_workers=rhel7_workers,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=data_volume_multi_storage_scope_function,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
        vm_cpu_model=nodes_common_cpu_model
        if request.param.get("set_vm_common_cpu")
        else None,
    ) as vm:
        yield vm


@pytest.fixture()
def golden_image_vm_instance_from_template_multi_storage_scope_function(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_multi_storage_scope_function,
    network_configuration,
    cloud_init_data,
    nodes_common_cpu_model,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=golden_image_data_volume_multi_storage_scope_function,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
        vm_cpu_model=nodes_common_cpu_model
        if request.param.get("set_vm_common_cpu")
        else None,
    ) as vm:
        yield vm


@pytest.fixture()
def golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_multi_storage_scope_class,
    network_configuration,
    cloud_init_data,
    nodes_common_cpu_model,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    VM is created with function scope whereas golden image DV is created with class scope. to be used when a number
    of tests (each creates its relevant VM) are gathered under a class and use the same golden image DV.
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=golden_image_data_volume_multi_storage_scope_class,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
        vm_cpu_model=nodes_common_cpu_model
        if request.param.get("set_vm_common_cpu")
        else None,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def vm_instance_from_template_multi_storage_scope_class(
    request,
    rhel7_workers,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_class,
    network_configuration,
    cloud_init_data,
    nodes_common_cpu_model,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        rhel7_workers=rhel7_workers,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=data_volume_multi_storage_scope_class,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
        vm_cpu_model=nodes_common_cpu_model
        if request.param.get("set_vm_common_cpu")
        else None,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def golden_image_vm_instance_from_template_multi_storage_scope_class(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_multi_storage_scope_class,
    network_configuration,
    cloud_init_data,
    nodes_common_cpu_model,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume=golden_image_data_volume_multi_storage_scope_class,
        network_configuration=network_configuration,
        cloud_init_data=cloud_init_data,
        vm_cpu_model=nodes_common_cpu_model
        if request.param.get("set_vm_common_cpu")
        else None,
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
        wait_timeout=10, sleep=1, func=lambda: default_sa.instance.secrets
    )
    for sample in sampler:
        if sample:
            return


@pytest.fixture()
def started_windows_vm(
    request,
    vm_instance_from_template_multi_storage_scope_function,
):
    wait_for_windows_vm(
        vm=vm_instance_from_template_multi_storage_scope_function,
        version=request.param["os_version"],
    )


def is_openshift(client):
    namespaces = [ns.name for ns in Namespace.get(client)]
    return "openshift-operators" in namespaces


@pytest.fixture(scope="session")
def skip_not_openshift(admin_client):
    """
    Skip test if tests run on kubernetes (and not openshift)
    """
    if not is_openshift(admin_client):
        pytest.skip("Skipping test requiring OpenShift")


@pytest.fixture(scope="session")
def worker_nodes_ipv4_false_secondary_nics(
    nodes_available_nics, schedulable_nodes, utility_pods
):
    """
    Function removes ipv4 from secondary nics.
    """
    for worker_node in schedulable_nodes:
        worker_nics = nodes_available_nics[worker_node.name]
        with EthernetNetworkConfigurationPolicy(
            name=f"disable-ipv4-{worker_node.name}",
            node_selector=worker_node.name,
            ipv4_dhcp=False,
            worker_pods=utility_pods,
            interfaces_name=worker_nics,
            node_active_nics=worker_nics,
        ):
            LOGGER.info(
                f"selected worker node - {worker_node.name} under NNCP selected NIC information - {worker_nics} "
            )


@pytest.fixture(scope="session")
def cnv_current_version(admin_client):
    for csv in ClusterServiceVersion.get(
        dyn_client=admin_client, namespace=py_config["hco_namespace"]
    ):
        return csv.instance.spec.version


@pytest.fixture(scope="module")
def kubevirt_config_cm():
    return ConfigMap(name="kubevirt-config", namespace=py_config["hco_namespace"])


@pytest.fixture(scope="session")
def hco_namespace(admin_client):
    return list(
        Namespace.get(
            dyn_client=admin_client,
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
def worker_node3(schedulable_nodes):
    # Get third worker nodes out of schedulable_nodes list
    return schedulable_nodes[2]


@pytest.fixture(scope="session")
def sriov_nodes_states(skip_when_no_sriov, admin_client):
    return list(
        SriovNetworkNodeState.get(
            dyn_client=admin_client, namespace=py_config["sriov_namespace"]
        )
    )


@pytest.fixture(scope="session")
def labeled_sriov_nodes(admin_client, sriov_nodes_states):
    sriov_nodes_editors = []
    for state in sriov_nodes_states:
        sriov_nodes_editors.append(
            ResourceEditor(
                {
                    Node(client=admin_client, name=state.name): {
                        "metadata": {
                            "labels": {
                                "feature.node.kubernetes.io/network-sriov.capable": "true"
                            }
                        }
                    }
                }
            )
        )
    for editor in sriov_nodes_editors:
        editor.update(backup_resources=True)
    yield
    for editor in sriov_nodes_editors:
        editor.restore()


@pytest.fixture(scope="session")
def sriov_workers(schedulable_nodes, labeled_sriov_nodes):
    sriov_worker_label = "feature.node.kubernetes.io/network-sriov.capable"
    yield [
        node
        for node in schedulable_nodes
        if node.labels.get(sriov_worker_label) == "true"
    ]


@pytest.fixture(scope="session")
def sriov_iface(sriov_nodes_states, workers_ssh_executors):
    for iface in sriov_nodes_states[0].instance.status.interfaces:
        if (
            iface.totalvfs
            and workers_ssh_executors[
                sriov_nodes_states[0].name
            ].network.get_interface_status(interface=iface.name)
            == "up"
        ):
            return iface
    raise NotFoundError(
        "no sriov interface with 'up' status was found, please make sure at least one sriov interface is up"
    )


def wait_for_ready_sriov_nodes(snns):
    for status in ("InProgress", "Succeeded"):
        for state in snns:
            state.wait_for_status_sync(wanted_status=status)


@pytest.fixture(scope="session")
def sriov_node_policy(sriov_nodes_states, sriov_iface):
    with network_device(
        interface_type=SRIOV,
        nncp_name="test-sriov-policy",
        namespace=py_config["sriov_namespace"],
        sriov_iface=sriov_iface,
        sriov_resource_name="sriov_net",
        # sriov operator doesnt pass the mtu to the VFs when using vfio-pci device driver (the one we are using)
        # so the mtu parameter only affects the PF. we need to change the mtu manually on the VM.
        mtu=9000,
    ) as policy:
        wait_for_ready_sriov_nodes(snns=sriov_nodes_states)
        yield policy
    wait_for_ready_sriov_nodes(snns=sriov_nodes_states)


@pytest.fixture(scope="session")
def bugzilla_connection_params(pytestconfig):
    return get_bugzilla_connection_params()


@pytest.fixture(scope="session")
def mac_pool(hco_namespace):
    return MacPool(
        kmp_range=ConfigMap(
            namespace=hco_namespace.name, name="kubemacpool-mac-range-config"
        ).instance["data"]
    )


def _skip_access_mode_rwo(storage_class_matrix):
    if (
        storage_class_matrix[[*storage_class_matrix][0]]["access_mode"]
        == PersistentVolumeClaim.AccessMode.RWO
    ):
        pytest.skip(
            msg="Skipping when access_mode is RWO; possible reason: cannot migrate VMI with non-shared PVCs"
        )


@pytest.fixture()
def skip_access_mode_rwo_scope_function(storage_class_matrix__function__):
    _skip_access_mode_rwo(storage_class_matrix=storage_class_matrix__function__)


@pytest.fixture(scope="class")
def skip_access_mode_rwo_scope_class(storage_class_matrix__class__):
    _skip_access_mode_rwo(storage_class_matrix=storage_class_matrix__class__)


@pytest.fixture(scope="session")
def nodes_common_cpu_model(schedulable_nodes):
    cpu_label_prefix = "feature.node.kubernetes.io/cpu-model-"
    # CPU families; descending
    # TODO: Add AMD models
    cpus_families_list = [
        "Cascadelake",
        "Skylake",
        "Broadwell",
        "Haswell",
        "IvyBridge",
        "SandyBridge",
        "Westmere",
    ]

    def _format_cpu_name(cpu_name):
        return re.match(rf"{cpu_label_prefix}(.*)", cpu_name).group(1)

    nodes_cpus_list = [
        [
            label
            for label, value in node.labels.items()
            if re.match(rf"{cpu_label_prefix}.*", label) and value == "true"
        ]
        for node in schedulable_nodes
    ]
    # Count how many times each model appears in the list of nodes cpus lists
    cpus_dict = Counter(cpu for node_cpus in nodes_cpus_list for cpu in set(node_cpus))

    # CPU model which is common for all nodes and a first match for cpu family in cpus_families_list
    for cpus_family in cpus_families_list:
        for cpu, counter in cpus_dict.items():
            if counter == len(schedulable_nodes) and cpus_family in cpu:
                return _format_cpu_name(cpu_name=cpu)


@pytest.fixture(scope="session")
def golden_images_namespace(
    admin_client,
):
    for ns in Namespace.get(
        name=py_config["golden_images_namespace"],
        dyn_client=admin_client,
    ):
        return ns


@pytest.fixture(scope="session")
def golden_images_cluster_role_edit(
    admin_client,
):
    for cluster_role in ClusterRole.get(
        name="os-images.kubevirt.io:edit",
        dyn_client=admin_client,
    ):
        return cluster_role


@pytest.fixture()
def golden_images_edit_rolebinding(
    golden_images_namespace,
    golden_images_cluster_role_edit,
):
    with RoleBinding(
        name="role-bind-create-dv",
        namespace=golden_images_namespace.name,
        subjects_kind="User",
        subjects_name="unprivileged-user",
        subjects_namespace=golden_images_namespace.name,
        role_ref_kind=golden_images_cluster_role_edit.kind,
        role_ref_name=golden_images_cluster_role_edit.name,
    ) as role_binding:
        yield role_binding


def config_default_storage_class(session):
    # Default storage class selection order:
    # 1. --default-storage-class from command line
    # 2. --storage-class-matrix:
    #     * if default sc from global_config storage_class_matrix appears in the commandline, use this sc
    #     * if default sc from global_config storage_class_matrix does not appear in the commandline, use the first
    #       sc in --storage-class-matrix options
    # 3. global_config default_storage_class
    global_config_default_sc = py_config["default_storage_class"]
    cmd_default_storage_class = session.config.getoption(name="default_storage_class")
    cmdline_storage_class_matrix = session.config.getoption(name="storage_class_matrix")
    updated_default_sc = None
    if cmd_default_storage_class:
        updated_default_sc = cmd_default_storage_class
    elif cmdline_storage_class_matrix:
        cmdline_storage_class_matrix = cmdline_storage_class_matrix.split(",")
        updated_default_sc = (
            global_config_default_sc
            if global_config_default_sc in cmdline_storage_class_matrix
            else cmdline_storage_class_matrix[0]
        )

    # Update only if the requested default sc is not the same as set in global_config
    if updated_default_sc and updated_default_sc != global_config_default_sc:
        py_config["default_storage_class"] = updated_default_sc
        default_storage_class_configuration = [
            sc_dict
            for sc in py_config["system_storage_class_matrix"]
            for sc_name, sc_dict in sc.items()
            if sc_name == updated_default_sc
        ][0]

        py_config["default_volume_mode"] = default_storage_class_configuration[
            "volume_mode"
        ]
        py_config["default_access_mode"] = default_storage_class_configuration[
            "access_mode"
        ]


@pytest.fixture(scope="session")
def hosts_common_available_ports(nodes_available_nics):
    """
    Get list of common ports from nodes_available_nics.

    nodes_available_nics like
    [['ens3', 'ens4', 'ens6', 'ens5'],
    ['ens3', 'ens8', 'ens6', 'ens7'],
    ['ens3', 'ens8', 'ens6', 'ens7']]

    will return ['ens3', 'ens6']
    """
    nics_list = list(
        set.intersection(*[set(_list) for _list in nodes_available_nics.values()])
    )
    LOGGER.info(f"Hosts common available NICs: {nics_list}")
    return nics_list


@pytest.fixture(scope="session")
def hosts_common_occupied_ports(nodes_occupied_nics):
    """
    Get list of common ports from nodes_occupied_nics.

    nodes_occupied_nics like
    [['ens3', 'ens4', 'ens6', 'ens5'],
    ['ens3', 'ens8', 'ens6', 'ens7'],
    ['ens3', 'ens8', 'ens6', 'ens7']]

    will return ['ens3', 'ens6']
    """
    nics_list = list(
        set.intersection(*[set(_list) for _list in nodes_occupied_nics.values()])
    )
    LOGGER.info(f"Hosts common occupied NICs: {nics_list}")
    return nics_list


@pytest.fixture(scope="session")
def default_sc(admin_client):
    """
    Get default Storage Class defined
    """
    default_sc_list = [
        sc
        for sc in StorageClass.get(dyn_client=admin_client)
        if sc.instance.metadata.get("annotations", {}).get(
            StorageClass.Annotations.IS_DEFAULT_CLASS
        )
        == "true"
    ]
    if default_sc_list:
        yield default_sc_list[0]
    else:
        yield


@pytest.fixture(scope="session")
def pyconfig_updated_default_sc(admin_client, default_sc):
    # Based on py_config["default_storage_class"], update default SC, if needed
    if default_sc:
        yield default_sc
    else:
        for sc in StorageClass.get(
            dyn_client=admin_client, name=py_config["default_storage_class"]
        ):
            assert (
                sc
            ), f'The cluster does not include {py_config["default_storage_class"]} storage class'
            with ResourceEditor(
                patches={
                    sc: {
                        "metadata": {
                            "annotations": {
                                StorageClass.Annotations.IS_DEFAULT_CLASS: "true"
                            },
                            "name": sc.name,
                        }
                    }
                }
            ):
                yield sc


@pytest.fixture()
def hyperconverged_resource(admin_client, hco_namespace):
    for hco in HyperConverged.get(
        dyn_client=admin_client,
        namespace=hco_namespace.name,
        name="kubevirt-hyperconverged",
    ):
        return hco


@pytest.fixture(scope="class")
def hyperconverged_resource_scope_class(admin_client, hco_namespace):
    for hco in HyperConverged.get(
        dyn_client=admin_client,
        namespace=hco_namespace.name,
        name="kubevirt-hyperconverged",
    ):
        return hco


@pytest.fixture(scope="session")
def skip_when_no_sriov(admin_client):
    try:
        list(
            CustomResourceDefinition.get(
                dyn_client=admin_client,
                name="sriovnetworknodestates.sriovnetwork.openshift.io",
            )
        )
    except NotFoundError:
        pytest.skip(msg="Cluster without SR-IOV support")


@pytest.fixture(scope="class")
def ovs_daemonset(admin_client, hco_namespace):
    return wait_for_ovs_daemonset_resource(
        admin_client=admin_client, hco_namespace=hco_namespace
    )


@pytest.fixture()
def hyperconverged_ovs_annotations_fetched(hyperconverged_resource):
    return (hyperconverged_resource.instance.to_dict()["metadata"]["annotations"]).get(
        "deployOVS"
    )


@pytest.fixture(scope="module")
def network_addons_config(admin_client):
    nac = list(NetworkAddonsConfig.get(dyn_client=admin_client))
    assert nac, "There should be one NetworkAddonsConfig CR."
    yield nac[0]


@pytest.fixture(scope="session")
def ocs_storage_class(admin_client):
    """
    Get the OCS storage class if configured
    """
    for sc in StorageClass.get(
        dyn_client=admin_client, name=StorageClass.Types.CEPH_RBD
    ):
        return sc


@pytest.fixture(scope="session")
def skip_test_if_no_ocs_sc(ocs_storage_class):
    """
    Skip test if no OCS storage class available
    """
    if not ocs_storage_class:
        pytest.skip("Skipping test, OCS storage class is not deployed")


@pytest.fixture()
def hyperconverged_ovs_annotations_enabled(
    admin_client,
    hco_namespace,
    hyperconverged_resource,
    network_addons_config,
):
    yield from enable_hyperconverged_ovs_annotations(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource,
        network_addons_config=network_addons_config,
    )

    wait_for_ovs_status(network_addons_config=network_addons_config, status=False)


@pytest.fixture(scope="session")
def cluster_storage_classes(admin_client):
    return list(StorageClass.get(dyn_client=admin_client))


@pytest.fixture()
def removed_default_storage_classes(admin_client, cluster_storage_classes):
    sc_resources = []
    for sc in cluster_storage_classes:
        if (
            sc.instance.metadata.get("annotations", {}).get(
                StorageClass.Annotations.IS_DEFAULT_CLASS
            )
            == "true"
        ):
            sc_resources.append(
                ResourceEditor(
                    patches={
                        sc: {
                            "metadata": {
                                "annotations": {
                                    StorageClass.Annotations.IS_DEFAULT_CLASS: "false"
                                },
                                "name": sc.name,
                            }
                        }
                    }
                )
            )
    for editor in sc_resources:
        editor.update(backup_resources=True)
    yield
    for editor in sc_resources:
        editor.restore()


@pytest.fixture(scope="class")
def hyperconverged_with_node_placement(
    request, admin_client, hco_namespace, hyperconverged_resource_scope_class
):
    """
    Update HCO CR with infrastructure and workloads spec.
    """
    infra_placement = request.param["infra"]
    workloads_placement = request.param["workloads"]

    LOGGER.info("Fetching HCO to save its initial node placement configuration ")
    initial_infra = hyperconverged_resource_scope_class.instance.to_dict()["spec"].get(
        "infra", {}
    )
    initial_workloads = hyperconverged_resource_scope_class.instance.to_dict()[
        "spec"
    ].get("workloads", {})
    yield apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_class,
        hco_namespace=hco_namespace,
        infra_placement=infra_placement,
        workloads_placement=workloads_placement,
    )
    LOGGER.info("Revert to initial HCO node placement configuration ")
    apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_class,
        hco_namespace=hco_namespace,
        infra_placement=initial_infra,
        workloads_placement=initial_workloads,
    )


@pytest.fixture(scope="module")
def hostpath_provisioner():
    yield HostPathProvisioner(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)


@pytest.fixture(scope="module")
def cnv_pods(admin_client):
    yield list(Pod.get(dyn_client=admin_client, namespace=py_config["hco_namespace"]))


@pytest.fixture(scope="module", autouse=True)
def cluster_sanity(nodes, cnv_pods, cluster_storage_classes):
    sc_names = [sc.name for sc in cluster_storage_classes]
    config_sc = list([[*csc][0] for csc in py_config["storage_class_matrix"]])
    exists_sc = [scn for scn in config_sc if scn in sc_names]
    assert len(config_sc) == len(
        exists_sc
    ), f"Cluster is missing storage some storage class. Expected {config_sc}, On cluster {exists_sc}"

    for node in nodes:
        node_name = node.name
        assert node.kubelet_ready, f"{node_name}is not in {node.Status.READY} state"
        assert (
            node.instance.spec.unschedulable is None
        ), f"{node_name} is un-schedulable"

    for pod in cnv_pods:
        pod_status = pod.instance.status.phase
        assert pod_status == pod.Status.RUNNING, f"{pod.name} status is: {pod_status}"
