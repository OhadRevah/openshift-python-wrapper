import pytest

from tests.install_upgrade_operators.pod_validation.utils import (
    validate_cnv_pods_priority_class_name_exists,
    validate_priority_class_value,
)


@pytest.mark.polarion("CNV-7261")
def test_pods_priority_class_name(cnv_pods):
    validate_cnv_pods_priority_class_name_exists(cnv_pods=cnv_pods)


@pytest.mark.polarion("CNV-7262")
def test_pods_priority_class_value(cnv_pods):
    validate_priority_class_value(cnv_pods=cnv_pods)
