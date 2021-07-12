import pytest
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from pytest_testconfig import py_config


@pytest.fixture()
def skip_rwo_default_access_mode():
    if py_config["default_access_mode"] == PersistentVolumeClaim.AccessMode.RWO:
        pytest.skip("Skipping, default storage access mode is RWO")
