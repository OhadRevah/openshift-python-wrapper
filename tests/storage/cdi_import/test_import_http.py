# -*- coding: utf-8 -*-

"""
Import from HTTP server
"""

import pytest

from pytest_testconfig import config as py_config
from resources.datavolume import ImportFromHttpDataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from tests.storage.utils import VirtualMachineWithDV
from utilities import console

QCOW_IMG = 'cirros-qcow2.img'
TAR_IMG = 'cirros-qcow2.tar.gz'
CLOUD_INIT_USER_DATA = r"""
            #!/bin/sh
            echo 'printed from cloud-init userdata'"""


def get_file_url(images_http_server, file_name):
    return f'{images_http_server}cdi-test-images/{file_name}'


@pytest.mark.parametrize(
    ('content_type', 'file_name'),
    [
        pytest.param(ImportFromHttpDataVolume.ContentType.KUBEVIRT, QCOW_IMG, marks=(pytest.mark.polarion("CNV-2143"))),
        pytest.param(ImportFromHttpDataVolume.ContentType.ARCHIVE, TAR_IMG, marks=(pytest.mark.polarion("CNV-2145"))),
    ],
    ids=["import_kubevirt_image", "import_archive_image"]
)
def test_successful_import(storage_ns, images_http_server, file_name, content_type):
    url = get_file_url(images_http_server, file_name)
    with ImportFromHttpDataVolume(
            name='import-http-dv', namespace=storage_ns.name, content_type=content_type, url=url, size='500Mi',
            storage_class=py_config['storage_defaults']['storage_class']) as dv:
        assert dv.wait_for_status(status='Succeeded', timeout=300)
        assert PersistentVolumeClaim(name='import-http-dv', namespace=storage_ns.name).bound()


@pytest.mark.parametrize(
    ('content_type', 'file_name'),
    [
        pytest.param(ImportFromHttpDataVolume.ContentType.ARCHIVE, QCOW_IMG, marks=(pytest.mark.polarion("CNV-2144"))),
        pytest.param(ImportFromHttpDataVolume.ContentType.KUBEVIRT, TAR_IMG, marks=(pytest.mark.polarion("CNV-2147"))),
    ],
    ids=["qcow_image_archive_content_type", "tar_image_kubevirt_content_type"]
)
def test_wrong_content_type(storage_ns, images_http_server, file_name, content_type):
    url = get_file_url(images_http_server, file_name)
    with ImportFromHttpDataVolume(
            name='import-http-dv', namespace=storage_ns.name, content_type=content_type, url=url, size='500Mi',
            storage_class=py_config['storage_defaults']['storage_class']) as dv:
        assert dv.wait_for_status(status='Failed', timeout=300)


@pytest.mark.parametrize(
    'content_type',
    [
        pytest.param(ImportFromHttpDataVolume.ContentType.KUBEVIRT, marks=(pytest.mark.polarion("CNV-1865"))),
        pytest.param(None, marks=(pytest.mark.polarion("CNV-1868"))),
    ]
)
def test_import_http_vm(storage_ns, images_http_server, content_type):
    with ImportFromHttpDataVolume(
            name='import-http-dv-cirros',
            namespace=storage_ns.name,
            content_type=content_type,
            url=get_file_url(images_http_server, QCOW_IMG),
            size='500Mi',
            storage_class=py_config['storage_defaults']['storage_class']) as dv:
        assert dv.wait_for_status(status='Succeeded', timeout=300)
        assert PersistentVolumeClaim(name=dv.name, namespace=storage_ns.name).bound()

        with VirtualMachineWithDV(name='cirros-vm', namespace=storage_ns.name,
                                  dv_name=dv.name, cloud_init_data=CLOUD_INIT_USER_DATA) as vm:
            assert vm.start()
            assert vm.vmi.wait_until_running()
            with console.Cirros(vm=vm.name, namespace=storage_ns.name) as vm_console:
                vm_console.sendline("lsblk | grep disk | wc -l")
                vm_console.expect("2", timeout=20)


@pytest.mark.parametrize(
    ('dv_name', 'file_name'),
    [
        pytest.param("large-size", "invalid-qcow-large-size.img", marks=(pytest.mark.polarion("CNV-2555"))),
        pytest.param("large-json", "invalid-qcow-large-json.img", marks=(pytest.mark.polarion("CNV-2554"))),
        pytest.param("large-memory", "invalid-qcow-large-memory.img", marks=(pytest.mark.polarion("CNV-2253"))),
        pytest.param("backing-file", "invalid-qcow-backing-file.img", marks=(pytest.mark.polarion("CNV-2139"))),
    ]
)
def test_import_invalid_qcow(storage_ns, images_http_server, dv_name, file_name):
    with ImportFromHttpDataVolume(
            name=dv_name, namespace=storage_ns.name,
            content_type=ImportFromHttpDataVolume.ContentType.KUBEVIRT,
            url=get_file_url(images_http_server, file_name), size="5Gi",
            storage_class=py_config['storage_defaults']['storage_class']) as dv:
        assert dv.wait_for_status(status=ImportFromHttpDataVolume.Status.FAILED, timeout=90)
