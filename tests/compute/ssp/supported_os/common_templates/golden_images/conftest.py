import pytest
from tests.conftest import vm_instance_from_template
from utilities.storage import data_volume_template_dict


@pytest.fixture()
def vm_instance_from_template_golden_image_multi_scope_function(
    request,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    worker_node1,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=data_volume_template_dict(
            target_dv_name=request.param["target_dv_name"],
            source_dv=data_volume_multi_storage_scope_function,
            worker_node=worker_node1,
        ),
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def vm_instance_from_template_golden_image_multi_scope_class(
    request,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_class,
    worker_node1,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=data_volume_template_dict(
            target_dv_name=request.param["target_dv_name"],
            source_dv=data_volume_multi_storage_scope_class,
            worker_node=worker_node1,
        ),
    ) as vm:
        yield vm
