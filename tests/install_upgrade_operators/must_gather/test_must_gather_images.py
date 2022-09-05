import pytest
from ocp_resources.image import Image
from ocp_resources.image_stream import ImageStream
from ocp_resources.imagestreamtag import ImageStreamTag

from tests.install_upgrade_operators.must_gather.utils import (
    VALIDATE_UID_NAME,
    check_list_of_resources,
)
from utilities.constants import OPENSHIFT_NAMESPACE


class TestImageGathering:
    @pytest.mark.parametrize(
        "resource, resource_name, finddirpath",
        [
            pytest.param(
                Image,
                "images",
                {"resource_path": "cluster-scoped-resources/images"},
                marks=(pytest.mark.polarion("CNV-9234")),
            ),
            pytest.param(
                ImageStream,
                "imagestreams",
                {"resource_path": f"namespaces/{OPENSHIFT_NAMESPACE}/imagestreams"},
                marks=(pytest.mark.polarion("CNV-9235")),
            ),
            pytest.param(
                ImageStreamTag,
                "imagestreamtags",
                {"resource_path": f"namespaces/{OPENSHIFT_NAMESPACE}/imagestreamtags"},
                marks=(pytest.mark.polarion("CNV-9236")),
            ),
        ],
        indirect=["finddirpath"],
    )
    def test_image_gather(
        self, admin_client, gathered_images, resource_name, resource, finddirpath
    ):
        check_list_of_resources(
            dyn_client=admin_client,
            resource_type=resource,
            temp_dir=gathered_images,
            resource_path=f"{finddirpath}/" "{name}.yaml",
            checks=VALIDATE_UID_NAME,
            filter_resource="redhat",
        )
