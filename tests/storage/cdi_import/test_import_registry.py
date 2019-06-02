# -*- coding: utf-8 -*-

import pytest

from pytest_testconfig import config as py_config
from tests.storage.utils import VirtualMachineWithDV
from utilities import console
from resources.datavolume import ImportFromRegistryDataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim


CLOUD_INIT_USER_DATA = r"""
            #!/bin/sh
            echo 'printed from cloud-init userdata'"""

DOCKERHUB_IMAGE = "docker://kubevirt/cirros-registry-disk-demo"
QUAY_IMAGE = "docker://quay.io/kubevirt/cirros-registry-disk-demo"


def create_dv_and_vm(dv_name, namespace, url, cert_configmap, content_type, size):
    with ImportFromRegistryDataVolume(
            name=dv_name,
            namespace=namespace,
            url=url,
            content_type=content_type,
            size=size,
            storage_class=py_config['storage_defaults']['storage_class'],
            cert_configmap=cert_configmap) as dv:
        assert dv.wait_for_status(status='Succeeded', timeout=300)
        assert PersistentVolumeClaim(name=dv_name, namespace=namespace).bound()

        with VirtualMachineWithDV(name='cirros-vm', namespace=namespace, dv_name=dv_name,
                                  cloud_init_data=CLOUD_INIT_USER_DATA) as vm:
            assert vm.start()
            assert vm.vmi.wait_until_running()
            with console.Cirros(vm=vm.name, namespace=namespace) as vm_console:
                vm_console.sendline("lsblk | grep disk | wc -l")
                vm_console.expect("2", timeout=60)


@pytest.mark.parametrize(
    ('dv_name', 'url', 'cert_configmap', 'content_type', 'size'),
    [
        pytest.param("import-registry-dockerhub-dv", DOCKERHUB_IMAGE, None,
                     ImportFromRegistryDataVolume.ContentType.KUBEVIRT, "5Gi",
                     marks=(pytest.mark.polarion("CNV-2149"))),
        pytest.param("import-registry-dockerhub-no-content-type-dv", DOCKERHUB_IMAGE,
                     None, None, "5Gi",  marks=(pytest.mark.polarion("CNV-2197"))),
        pytest.param("import-registry-dockerhub-empty-content-type-dv", DOCKERHUB_IMAGE,
                     None, "", "5Gi",  marks=(pytest.mark.polarion("CNV-2195"))),
        pytest.param("import-registry-quay-dv", QUAY_IMAGE, None,
                     ImportFromRegistryDataVolume.ContentType.KUBEVIRT, "5Gi",
                     marks=(pytest.mark.polarion("CNV-2026"))),

    ],
    ids=["import-registry-dockerhub-dv", "import-registry-dockerhub-no-content-type-dv",
         "import-registry-dockerhub-empty-content-type-dv", "import-registry-quay-dv"]
)
def test_public_registry_data_volume(storage_ns, dv_name, url, cert_configmap, content_type, size):
    create_dv_and_vm(dv_name, storage_ns.name, url, cert_configmap, content_type, size)


# The following test is to show after imports fails because low capacity storage,
# we can overcome by updaing to the right requested volume size and import successfully
@pytest.mark.polarion('CNV-2024')
def test_public_registry_data_volume_dockerhub_low_capacity(storage_ns):
    # negative flow - low capacity volume
    with ImportFromRegistryDataVolume(
            name="import-registry-dockerhub-low-capacity-dv",
            namespace=storage_ns.name,
            url=DOCKERHUB_IMAGE,
            content_type="",
            size="10Mi",
            storage_class=py_config['storage_defaults']['storage_class'],
            cert_configmap=None) as dv:
        assert dv.wait_for_status(status='Failed', timeout=300)

    # positive flow
    create_dv_and_vm("import-registry-dockerhub-low-capacity-dv", storage_ns.name,
                     DOCKERHUB_IMAGE, None,
                     ImportFromRegistryDataVolume.ContentType.KUBEVIRT, "5Gi")


@pytest.mark.polarion('CNV-2150')
def test_public_registry_data_volume_dockerhub_archive(storage_ns):
    with ImportFromRegistryDataVolume(
            name="import-registry-archive",
            namespace=storage_ns.name,
            url=DOCKERHUB_IMAGE,
            content_type=ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
            size='5Gi',
            storage_class=py_config['storage_defaults']['storage_class'],
            cert_configmap=None) as dv:
        assert dv is None
