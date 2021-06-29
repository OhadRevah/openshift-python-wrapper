import pytest
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from pytest_testconfig import py_config


def _skip_rwo_default_access_mode():
    if py_config["default_access_mode"] == PersistentVolumeClaim.AccessMode.RWO:
        pytest.skip("Skipping, default storage access mode is RWO")


@pytest.fixture()
def skip_rwo_default_access_mode_scope_function():
    _skip_rwo_default_access_mode()


@pytest.fixture(scope="module")
def skip_rwo_default_access_mode_scope_module():
    _skip_rwo_default_access_mode()
