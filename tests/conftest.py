# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV tests
"""
import base64
import bcrypt
import os
from subprocess import check_output, CalledProcessError

import kubernetes
import pytest
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError
from resources.node import Node
from resources.secret import Secret
from resources.namespace import Namespace
from resources.oauth import OAuth
from tests import utils as test_utils


UNPRIVILEGED_USER = "unprivileged-user"
UNPRIVILEGED_PASSWORD = "unprivileged-password"


class LoginError(Exception):
    pass


def pytest_collection_modifyitems(session, config, items):
    """
    Add polarion test case it from tests to junit xml
    """
    for item in items:
        for marker in item.iter_markers(name="polarion"):
            test_id = marker.args[0]
            item.user_properties.append(("polarion-testcase-id", test_id))

        for marker in item.iter_markers(name="bugzilla"):
            test_id = marker.args[0]
            item.user_properties.append(("bugzilla", test_id))

        for marker in item.iter_markers(name="jira"):
            test_id = marker.args[0]
            item.user_properties.append(("jira", test_id))


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


def login_to_account(api_address, user, password=None):
    """
    Helper function for login. Raise exception if login failed
    """
    login_command = f"oc login {api_address} -u {user}"
    if password:
        login_command += f" -p {password}"
    try:
        check_output(login_command, shell=True)
    except CalledProcessError as exc:
        raise LoginError(
            f"Error to login to {user} account due to the following error:\n {exc.output}"
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


@pytest.fixture(scope="session", autouse=True)
def openshift_platform():
    try:
        Namespace(name="openshift").instance
        return True
    except NotFoundError:
        return False


@pytest.fixture(scope="session")
def unprivileged_secret(default_client):
    password = UNPRIVILEGED_PASSWORD.encode()
    enc_password = bcrypt.hashpw(password, bcrypt.gensalt(5))
    crypto_credentials = f"{UNPRIVILEGED_USER}:{enc_password}".encode()
    with Secret(
        name="htpass-secret",
        namespace="openshift-config",
        htpasswd=base64.b64encode(crypto_credentials).decode(),
    ):
        yield


@pytest.fixture(scope="session", autouse=True)
def unprivileged_client(unprivileged_secret, default_client, openshift_platform):
    """
    Provides none privilege API client
    """
    if not openshift_platform:
        return None
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
    login_to_account(
        api_address=default_client.configuration.host,
        user=UNPRIVILEGED_USER,
        password=UNPRIVILEGED_PASSWORD,
    )  # Login to unprivileged account
    token = check_output("oc whoami -t", shell=True).decode().strip("\n")  # Get token
    login_to_account(
        api_address=default_client.configuration.host, user="system:admin"
    )  # Get back to admin account
    token_auth = {
        "api_key": {"authorization": f"Bearer {token}"},
        "host": default_client.configuration.host,
        "verify_ssl": False,
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
    yield list(
        Node.get(
            dyn_client=default_client, label_selector="kubevirt.io/schedulable=true"
        )
    )


@pytest.fixture()
def images_external_http_server():
    return test_utils.get_images_external_http_server()


@pytest.fixture()
def images_https_server():
    return test_utils.get_images_https_server()
