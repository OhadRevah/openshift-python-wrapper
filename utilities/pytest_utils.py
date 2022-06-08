import importlib
import logging
import os
import re
import shutil
import socket
import sys
import time

import rrmngmnt
import yaml
from pytest_testconfig import config as py_config

from utilities.constants import KUBECONFIG


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
    skip_dynamic_matrix = (
        pytest_config.getoption("--collect-only")
        or pytest_config.getoption("--setup-plan")
        or py_config["distribution"] == "upstream"
    )

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
        if skip_dynamic_matrix:
            _matrix_params = _base_matrix_params

        else:
            module_name = "utilities.pytest_matrix_utils"
            if module_name not in sys.modules:
                sys.modules[module_name] = importlib.import_module(name=module_name)

            pytest_matrix_utils = sys.modules[module_name]
            matrix_func = getattr(pytest_matrix_utils, _matrix_func_name)
            _matrix_params = matrix_func(matrix=_base_matrix_params)

    if not _matrix_params:
        raise ValueError(missing_matrix_error)

    return _matrix_params if isinstance(_matrix_params, list) else [_matrix_params]


def save_pytest_execution_info(session, stage):
    """
    Save pytest execution info to a file.

    The files will be saved under:
    https://cnv-qe-server.rhevdev.lab.eng.rdu2.redhat.com/files/cnv-tests/pytest-executions/
    in format:
        <cluster name>/<start/end>-uuid

    Args:
        session (Session): pytest Session object.
        stage (str): pytest stage (session start or end).
    """
    remote_host_file = py_config["servers_url"]["USA"]
    LOGGER.info("Starting process of saving pytest execution info.")
    try:
        if session.config.getoption("--collect-only") or session.config.getoption(
            "--setup-plan"
        ):
            return

        kubeconfig = os.getenv(KUBECONFIG)
        if not (kubeconfig and os.path.exists(kubeconfig)):
            return

        with open(kubeconfig, "r") as fd:
            kubeconfig_dict = yaml.safe_load(fd)
            cluster_name = kubeconfig_dict["clusters"][0]["name"]

        time_now = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.gmtime())
        pytest_command_line_args = " ".join(session.config.invocation_params.args)
        pytest_execution_folder_name = "pytest-executions"
        local_hostname = socket.gethostname()

        # Local folders
        local_dst_base_folder = os.path.join(
            os.path.expanduser("~"), pytest_execution_folder_name
        )
        local_dst_folder_cluster_name = os.path.join(
            local_dst_base_folder, cluster_name
        )
        local_dst_file_path = os.path.join(
            local_dst_folder_cluster_name, session.config.option.session_id
        )

        # Remote folders
        remote_dst_bash_folder = (
            f"/var/www/files/cnv-tests/{pytest_execution_folder_name}"
        )
        remote_dst_folder_cluster_name = os.path.join(
            remote_dst_bash_folder, cluster_name
        )

        # Connection to web server
        host = rrmngmnt.Host(hostname=remote_host_file)
        host.users.append(rrmngmnt.RootUser("redhat"))

        # Create folders in web server
        for _path in (remote_dst_bash_folder, remote_dst_folder_cluster_name):
            if not host.fs.isdir(_path):
                host.fs.mkdir(path=_path)

        # Create local folders
        if not os.path.isdir(local_dst_folder_cluster_name):
            os.makedirs(local_dst_folder_cluster_name)

        session_info = f"#### {stage} at {time_now} ####\n\n"
        if stage == "start":
            session_info = (
                f"{session_info}"
                f"Cluster: {cluster_name}\n"
                f"Executed from: {local_hostname}\n"
                f"Pytest command line: {pytest_command_line_args}\n"
            )

        os.system(f"echo '{session_info}' >> {local_dst_file_path}")
        host.fs.put(
            path_src=local_dst_file_path, path_dst=remote_dst_folder_cluster_name
        )
    except Exception as exp:
        LOGGER.exception(exp)

    LOGGER.info(f"Pytest execution info saved to {remote_host_file}.")


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
