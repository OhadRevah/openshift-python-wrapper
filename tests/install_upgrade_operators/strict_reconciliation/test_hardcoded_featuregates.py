import pytest

from tests.install_upgrade_operators.strict_reconciliation import constants
from tests.install_upgrade_operators.strict_reconciliation.utils import (
    create_rpatch_dict,
)
from tests.install_upgrade_operators.utils import (
    get_hyperconverged_cdi,
    get_hyperconverged_kubevirt,
    wait_for_stabilize,
)


class TestHardcodedFeatureGates:
    @pytest.mark.parametrize(
        ("updated_delete_resource", "expected"),
        [
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            "configuration": {
                                "developerConfiguration": {"featureGates": None}
                            }
                        }
                    },
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6427")),
                id="delete_hardcoded_featuregates_kubevirt_cr_featuregates_none",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            "configuration": {
                                "developerConfiguration": {"featureGates": []}
                            }
                        }
                    },
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6428")),
                id="delete_hardcoded_featuregates_kubevirt_cr_featuregates_empty_list",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {"configuration": {"developerConfiguration": None}}
                    },
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6429")),
                id="delete_hardcoded_featuregates_kubevirt_cr_developerConfiguration_none",
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {"configuration": {"developerConfiguration": {}}}
                    },
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6430")),
                id="delete_hardcoded_featuregates_kubevirt_cr_developerConfiguration_empty_dict",
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {"configuration": None}},
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6431")),
                id="delete_hardcoded_featuregates_kubevirt_cr_configuration_none",
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {"configuration": {}}},
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6435")),
                id="delete_hardcoded_featuregates_kubevirt_cr_configuration_empty_dict",
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {}},
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6639")),
                id="delete_hardcoded_featuregates_kubevirt_cr_spec_empty_dict",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["DataVolumes"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6436")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_datavolumes",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["SRIOV"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6437")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_sriov",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["LiveMigration"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6438")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_livemigration",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["CPUManager"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6439")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_cpumanager",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["CPUNodeDiscovery"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6440")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_cpunodediscovery",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["Snapshot"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6441")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_snapshot",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["HotplugVolumes"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6442")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_hotplugvolumes",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["GPU"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6443")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_gpu",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["HostDevices"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6444")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_hostdevices",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["WithHostModelCPU"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6445")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_withhostmodelcpu",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(["HypervStrictCheck"]),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6446")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_hyperstrictcheck",
            ),
            pytest.param(
                {
                    "rpatch": create_rpatch_dict(
                        ["DataVolumes", "Snapshot", "HypervStrictCheck"]
                    ),
                    "related_object_name": "kubevirt-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_kubevirt,
                },
                constants.EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6447")),
                id="delete_hardcoded_featuregates_kubevirt_cr_remove_datavolumes_snapshot_hypervstrictcheck",
            ),
        ],
        indirect=["updated_delete_resource"],
    )
    def test_hardcoded_featuregates_removed_from_kubevirt_cr(
        self,
        admin_client,
        hco_namespace,
        updated_delete_resource,
        expected,
        kubevirt_hyperconverged_spec_scope_function,
    ):
        actual_fgs = kubevirt_hyperconverged_spec_scope_function["configuration"][
            "developerConfiguration"
        ]["featureGates"]
        assert (
            actual_fgs == expected
        ), "actual featureGates list in KubeVirt CR is not as expected: "
        f"expected={expected} actual={actual_fgs}"

    @pytest.mark.polarion("CNV-6277")
    @pytest.mark.parametrize(
        ("updated_cdi_cr", "expected"),
        [
            pytest.param(
                {
                    "patch": {"spec": {"config": {"featureGates": None}}},
                    "related_object_name": "cdi-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_cdi,
                },
                constants.EXPECTED_CDI_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6449")),
                id="delete_hardcoded_featuregates_cdi_cr_featuregates_none",
            ),
            pytest.param(
                {
                    "patch": {"spec": {"config": {"featureGates": []}}},
                    "related_object_name": "cdi-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_cdi,
                },
                constants.EXPECTED_CDI_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6450")),
                id="delete_hardcoded_featuregates_cdi_cr_featuregates_empty_list",
            ),
            pytest.param(
                {
                    "patch": {"spec": {"config": None}},
                    "related_object_name": "cdi-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_cdi,
                },
                constants.EXPECTED_CDI_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6451")),
                id="delete_hardcoded_featuregates_cdi_cr_config_none",
            ),
            pytest.param(
                {
                    "patch": {"spec": {"config": {}}},
                    "related_object_name": "cdi-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_cdi,
                },
                constants.EXPECTED_CDI_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6452")),
                id="delete_hardcoded_featuregates_cdi_cr_config_empty_dict",
            ),
            pytest.param(
                {
                    "patch": {"spec": {}},
                    "related_object_name": "cdi-kubevirt-hyperconverged",
                    "resource_func": get_hyperconverged_cdi,
                },
                constants.EXPECTED_CDI_HARDCODED_FEATUREGATES,
                marks=(pytest.mark.polarion("CNV-6640")),
                id="delete_hardcoded_featuregates_cdi_cr_spec_empty_dict",
            ),
        ],
        indirect=["updated_cdi_cr"],
    )
    def test_hardcoded_featuregates_removed_from_cdi_cr(
        self,
        admin_client,
        hco_namespace,
        updated_cdi_cr,
        expected,
    ):
        wait_for_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)
        cdi_resource = get_hyperconverged_cdi(admin_client=admin_client)
        actual_fgs = cdi_resource.instance.to_dict()["spec"]["config"]["featureGates"]
        assert (
            actual_fgs == expected
        ), "actual featureGates list in CDI CR is not as expected: "
        f"expected={expected} actual={actual_fgs}"
