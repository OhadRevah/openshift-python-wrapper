# -*- coding: utf-8 -*-

"""
Common templates test
"""
import pytest
from resources.datavolume import ImportFromHttpDataVolume
from resources.namespace import Namespace
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.template import Template
from resources.virtual_machine import VirtualMachine
from utilities import console
from pytest_testconfig import config as py_config
from tests import utils as test_utils
from tests.virt import config as virt_config

VM_NAME = "virt-common-templates-test"


class VirtualMachineFromTemplate(VirtualMachine):
    def __init__(self, name, namespace, body):
        super().__init__(name=name, namespace=namespace)
        self.body = body

    def _to_dict(self):
        return self.body


class DataVolumeTestResource(ImportFromHttpDataVolume):
    def __init__(
        self,
        name,
        namespace,
        url,
        os_release,
        template_name,
        size="25Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
    ):
        super().__init__(name, namespace, url, content_type, size, storage_class)
        self.os_release = os_release
        self.template_name = template_name


@pytest.fixture(scope="module", autouse=True)
def http_server():
    return test_utils.get_images_http_server()


@pytest.fixture(scope="module", autouse=True)
def namespace():
    with Namespace(name="common-templates-test") as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE)
        yield ns


@pytest.fixture(
    params=[
        pytest.param(
            ["rhel-images/rhel-76/rhel-76.qcow2", "7.6", "rhel7-server-tiny"],
            marks=(pytest.mark.polarion("CNV-2174")),
        ),
        pytest.param(
            ["rhel-images/rhel-8/rhel-8.qcow2", "8.0", "rhel8-server-tiny"],
            marks=(pytest.mark.polarion("CNV-2210")),
        ),
        pytest.param(
            ["rhel-images/rhel-610/rhel-610.qcow2", "6", "rhel6-server-tiny"],
            marks=(pytest.mark.polarion("CNV-2211")),
        ),
    ]
)
def data_volume(request, http_server, namespace):
    template_name = request.param[2]
    with DataVolumeTestResource(
        name=f"dv-{template_name}",
        namespace=namespace.name,
        url=f"{http_server}{request.param[0]}",
        os_release=request.param[1],
        template_name=template_name,
    ) as dv:
        dv.wait_for_status(
            status=ImportFromHttpDataVolume.Status.SUCCEEDED, timeout=300
        )
        assert PersistentVolumeClaim(name=dv.name, namespace=namespace.name).bound()
        yield dv


def test_common_templates_with_rhel(data_volume, namespace):
    """
    Test CNV common templates with RHEL
    """
    template_instance = Template(name=data_volume.template_name, namespace="openshift")
    resources_list = template_instance.process(
        **{"NAME": VM_NAME, "PVCNAME": data_volume.name}
    )
    for resource in resources_list:
        if (
            resource["kind"] == VirtualMachine.kind
            and resource["metadata"]["name"] == VM_NAME
        ):
            with VirtualMachineFromTemplate(
                name=VM_NAME, namespace=namespace.name, body=resource
            ) as vm:
                vm.start()
                vm.vmi.wait_until_running()
                with console.Fedora(
                    vm=vm, username="cloud-user", password="redhat", timeout=1100
                ) as vm_console:
                    vm_console.sendline(
                        f"cat /etc/redhat-release | grep {data_volume.os_release} | wc -l\n"
                    )
                    vm_console.expect("1", timeout=60)
                vm.stop(wait=True)


@pytest.fixture()
def get_base_templates(default_client):
    """ Return templates list by label """
    yield [
        template.name
        for template in list(
            Template.get(
                default_client,
                singular_name="template",
                label_selector="template.kubevirt.io/type=base",
            )
        )
    ]


@pytest.mark.polarion("CNV-1069")
def test_base_templates_annotations(get_base_templates):
    """
    Check all CNV templates exists, by label: template.kubevirt.io/type=base
    """
    missing_templates = set(virt_config.CNV_TEMPLATES_NAME) - set(get_base_templates)
    new_changed_templates = set(get_base_templates) - set(
        virt_config.CNV_TEMPLATES_NAME
    )

    assert len(missing_templates) == 0, f"Missing templates {missing_templates}"
    assert (
        len(new_changed_templates) == 0
    ), f"Found new/changed templates {new_changed_templates}"
