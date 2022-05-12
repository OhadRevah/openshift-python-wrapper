from pytest_testconfig import config as py_config


IUO_UPGRADE_TEST_ORDERING_NODE_ID = IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID = (
    "tests/install_upgrade_operators/product_upgrade/test_upgrade.py::TestUpgrade::"
    f"test_{py_config['upgraded_product']}_upgrade_process"
)
COMPUTE_VMS_RUNNING_AFTER_UPGRADE_TEST_NODE_ID = (
    "tests/compute/upgrade/test_upgrade_compute.py::TestUpgradeCompute::"
    "test_is_vm_running_after_upgrade"
)
IUO_CNV_POD_ORDERING_NODE_ID = (
    "tests/install_upgrade_operators/product_upgrade/test_upgrade_iuo.py::TestUpgradeIUO::"
    "test_cnv_pods_running_after_upgrade"
)
