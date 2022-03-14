from pytest_testconfig import config as py_config


UPGRADE_TEST_ORDERING_NODE_ID = UPGRADE_TEST_DEPENDENCY_NODE_ID = (
    "tests/install_upgrade_operators/product_upgrade/test_upgrade.py::TestUpgrade::"
    f"test_{py_config['upgraded_product']}_upgrade_process"
)
