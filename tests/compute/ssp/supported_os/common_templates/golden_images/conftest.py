import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass


@pytest.fixture()
def updated_default_storage_class_scope_function(
    admin_client,
    storage_class_matrix__function__,
    removed_default_storage_classes,
):
    sc_name = [*storage_class_matrix__function__][0]
    sc = StorageClass(name=sc_name)
    with ResourceEditor(
        patches={
            sc: {
                "metadata": {
                    "annotations": {StorageClass.Annotations.IS_DEFAULT_CLASS: "true"},
                    "name": sc_name,
                }
            }
        }
    ):
        yield sc
