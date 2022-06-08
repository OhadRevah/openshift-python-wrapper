import importlib
import re
import sys

from pytest_testconfig import config as py_config


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
