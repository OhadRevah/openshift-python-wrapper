# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV tests
"""
import base64
import logging
import os
import os.path
import re
import urllib.request
from subprocess import PIPE, CalledProcessError, Popen, check_output

import bcrypt
import kubernetes
import pytest
from openshift.dynamic import DynamicClient
from pytest_testconfig import config as py_config
from resources.daemonset import DaemonSet
from resources.node import Node
from resources.node_network_state import NodeNetworkState
from resources.oauth import OAuth
from resources.pod import Pod
from resources.secret import Secret
from resources.utils import TimeoutSampler
from utilities.infra import (
    create_ns,
    generate_yaml_from_template,
    get_images_external_http_server,
    get_images_https_server,
)
from utilities.virt import kubernetes_taint_exists


LOGGER = logging.getLogger(__name__)
UNPRIVILEGED_USER = "unprivileged-user"
UNPRIVILEGED_PASSWORD = "unprivileged-password"


def pytest_addoption(parser):
    parser.addoption(
        "--upgrade", action="store_true", default=False, help="Run upgrade tests"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "upgrade: Upgrade tests")


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
            scope="module",
        )


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
    return DynamicClient(kubernetes.config.new_client_from_config())


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
    login_to_account(
        api_address=default_client.configuration.host,
        user=UNPRIVILEGED_USER,
        password=UNPRIVILEGED_PASSWORD,
    )  # Login to unprivileged account
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
def schedulable_node_ips(nodes):
    """
    Store all kubevirt.io/schedulable=true IPs
    """
    node_ips = {}
    for node in nodes:
        for addr in node.instance.status.addresses:
            if addr.type == "InternalIP":
                node_ips[node.name] = addr.address
    return node_ips


@pytest.fixture(scope="session")
def skip_when_one_node(nodes):
    if len(nodes) < 2:
        pytest.skip(msg="Test requires at least 2 nodes")


@pytest.fixture(scope="session")
def nodes(default_client):
    yield [
        node
        for node in list(
            Node.get(
                dyn_client=default_client, label_selector="kubevirt.io/schedulable=true"
            )
        )
        if not node.instance.spec.unschedulable and not kubernetes_taint_exists(node)
    ]


@pytest.fixture()
def images_external_http_server():
    return get_images_external_http_server()


@pytest.fixture()
def images_https_server():
    return get_images_https_server()


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
def network_utility_pods(net_utility_daemonset, default_client):
    """
    Get network utility pods.
    When the tests start we deploy a pod on every host in the cluster using a daemonset.
    These pods have a label of cnv-test=net-utility and they are privileged pods with hostnetwork=true
    """
    return list(Pod.get(default_client, label_selector="cnv-test=net-utility"))


@pytest.fixture(scope="session")
def nodes_active_nics(nodes):
    """
    Get nodes active NICs.
    First NIC is management NIC
    """
    nodes_nics = {}
    for node in nodes:
        nns = NodeNetworkState(name=node.name)
        ifaces = [iface.name for iface in nns.interfaces if iface.type == "ethernet"]
        default_routes = [
            route for route in nns.routes.running if route.destination == "0.0.0.0/0"
        ]
        lowest_metric = min([route.metric for route in default_routes])
        primary_iface_name = [
            route["next-hop-interface"]
            for route in default_routes
            if route.metric == lowest_metric
        ]
        primary_iface = [iface for iface in ifaces if iface == primary_iface_name[0]]
        primary_iface_idx = ifaces.index(primary_iface[0])
        if primary_iface_idx == 0:
            nodes_nics[node.name] = ifaces
        else:
            ifaces.pop(primary_iface_idx)
            nodes_nics[node.name] = primary_iface
            nodes_nics[node.name].append(ifaces)

    return nodes_nics


@pytest.fixture(scope="session")
def multi_nics_nodes(nodes_active_nics):
    """
    Check if nodes has more then 1 active NIC
    """
    # Set multi NICs to False since we have issues with multi NICs in PSI
    # https://jira.coreos.com/browse/CNV-3456
    return False
    # return min(len(nics) for nics in nodes_active_nics.values()) > 2


class NetUtilityDaemonSet(DaemonSet):
    def _to_dict(self):
        res = super()._to_dict()
        res.update(
            generate_yaml_from_template(
                file_=os.path.join(
                    os.path.dirname(__file__), "net-utility-daemonset.yaml"
                )
            )
        )
        return res


@pytest.fixture(scope="session", autouse=True)
def cnv_containers():
    res = {}
    if py_config["distribution"] == "upstream":
        return res

    data = urllib.request.urlopen(
        "http://download-node-02.eng.bos.redhat.com/rhel-8/nightly/CNV/latest-CNV-2-RHEL-8/containers.list",
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
