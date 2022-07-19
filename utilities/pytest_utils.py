import getpass
import importlib
import logging
import os
import re
import shutil
import socket
import sys

from ocp_resources.configmap import ConfigMap
from pytest_testconfig import config as py_config

from utilities.constants import CNV_TESTS_CONTAINER
from utilities.infra import exit_pytest_execution, get_kube_system_namespace


LOGGER = logging.getLogger(__name__)


def get_base_matrix_name(matrix_name):
    match = re.match(r".*?(.*?_matrix)_(?:.*_matrix)+", matrix_name)
    if match:
        return match.group(1)

    return matrix_name


def get_matrix_params(pytest_config, matrix_name):
    """
    Customize matrix based on existing matrix
    Name should be <base_matrix><_extra_matrix>_<scope>
    base_matrix should exist in py_config.
    _extra_matrix should be a function in utilities.pytest_matrix_utils

    Args:
       pytest_config (_pytest.config.Config): pytest config
       matrix_name (str): matrix name

    Example:
       storage_class_matrix_snapshot_matrix__class__

       storage_class_matrix is in py_config
       snapshot_matrix is a function in utilities.pytest_matrix_utils
       all function in utilities.pytest_matrix_utils accept only matrix args.

    Returns:
         list: list of matrix params
    """
    missing_matrix_error = f"{matrix_name} is missing in config file"
    base_matrix_name = get_base_matrix_name(matrix_name=matrix_name)

    _matrix_params = py_config.get(matrix_name)
    # If matrix is not in py_config, check if it is a function in utilities.pytest_matrix_utils
    if not _matrix_params:
        _matrix_func_name = matrix_name.split(base_matrix_name)[-1].replace("_", "", 1)
        _base_matrix_params = py_config.get(base_matrix_name)
        if not _base_matrix_params:
            raise ValueError(missing_matrix_error)

        # When running --collect-only or --setup-plan we cannot execute functions from pytest_matrix_utils
        if skip_if_pytest_flags_exists(pytest_config=pytest_config, skip_upstream=True):
            _matrix_params = _base_matrix_params

        else:
            module_name = "utilities.pytest_matrix_utils"
            if module_name not in sys.modules:
                sys.modules[module_name] = importlib.import_module(name=module_name)

            pytest_matrix_utils = sys.modules[module_name]
            matrix_func = getattr(pytest_matrix_utils, _matrix_func_name)
            return matrix_func(matrix=_base_matrix_params)

    if not _matrix_params:
        raise ValueError(missing_matrix_error)

    return _matrix_params if isinstance(_matrix_params, list) else [_matrix_params]


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


def separator(symbol_, val=None):
    terminal_width = shutil.get_terminal_size(fallback=(120, 40))[0]
    if not val:
        return f"{symbol_ * terminal_width}"

    sepa = int((terminal_width - len(val) - 2) // 2)
    return f"{symbol_ * sepa} {val} {symbol_ * sepa}"


def reorder_early_fixtures(metafunc):
    """
    Put fixtures with `pytest.mark.early` first during execution

    This allows patch of configurations before the application is initialized
    """
    for fixturedef in metafunc._arg2fixturedefs.values():
        fixturedef = fixturedef[0]
        for mark in getattr(fixturedef.func, "pytestmark", []):
            if mark.name == "early":
                order = metafunc.fixturenames
                order.insert(0, order.pop(order.index(fixturedef.argname)))
                break


def stop_if_run_in_progress():
    run_in_progress = run_in_progress_config_map()
    if run_in_progress.exists:
        exit_pytest_execution(
            message=f"cnv-tests run already in progress: \n{run_in_progress.instance.data}"
            f"\nAfter verifying no one else is performing tests against the cluster, run:"
            f"\n'oc delete configmap -n {run_in_progress.namespace} {run_in_progress.name}'",
        )


def deploy_run_in_progress_config_map(session):
    run_in_progress_config_map(session=session).deploy()


def run_in_progress_config_map(session=None):
    return ConfigMap(
        name="cnv-tests-run-in-progress",
        namespace=get_kube_system_namespace().name,
        data=get_current_running_data(session=session) if session else None,
    )


def get_current_running_data(session):
    return {
        "user": getpass.getuser(),
        "host": socket.gethostname(),
        "running_from_dir": os.getcwd(),
        "pytest_cmd": ", ".join(session.config.invocation_params.args),
        "session-id": session.config.option.session_id,
        "run-in-container": os.environ.get(CNV_TESTS_CONTAINER, "No"),
    }


def skip_if_pytest_flags_exists(pytest_config, skip_upstream=False):
    """
    In some cases we want to skip some operation when pytest got executed with some flags
    Used in dynamic fixtures and in check if run already in progress.

    Args:
        pytest_config (_pytest.config.Config): Pytest config object
        skip_upstream (bool): If True, skip if py_config if contains "upstream"

    Returns:
        bool: True if skip is needed, otherwise False
    """
    return (
        pytest_config.getoption("--collect-only")
        or pytest_config.getoption("--setup-plan")
        or (py_config["distribution"] == "upstream" if skip_upstream else False)
    )


def get_cnv_qe_server_url(cluster_host_url):
    """
    Get the relevant cnv-qe-server for the cluster.
    This solves two problems:
    1) Pulling and downloading the images from a relatively close server.
    2) There are cnv-qe-servers that are hosted inside of RH internal network,
       external clusters won't be able to access the server.

    List of servers are taken from:
    https://gitlab.cee.redhat.com/contra/cnv/-/blob/master/docs/Configure-cnv-qe-server.md#existing-instances

    Args:
        cluster_host_url (str): Cluster's API hostname.

    Returns:
        str: cnv-qe-server in the same region of the cluster.
    """
    default_server = "cnv-qe-server.rhevdev.lab.eng.rdu2.redhat.com"
    ibm_server = f"cnv-qe-server.{cluster_host_url.replace('https://api.', '').replace(':6443', '')}"
    rhood_server = "cnv-qe-server.cnv-qe.rhood.us"
    servers = {
        "ibmc.cnv-qe.rhood.us": ibm_server,
        "ibmc-upi.cnv-qe.rhood.us": ibm_server,
        "qe.azure.devcluster.openshift.com": rhood_server,
        "cnv-qe.rhood.us": rhood_server,
        "lab.eng.tlv2.redhat.com": "cnv-qe-server.lab.eng.tlv2.redhat.com",
    }

    for domain, server in servers.items():
        if domain in cluster_host_url:
            return server

    return default_server
