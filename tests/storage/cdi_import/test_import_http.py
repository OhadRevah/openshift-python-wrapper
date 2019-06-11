# -*- coding: utf-8 -*-

"""
Import from HTTP server
"""

import pytest

from pytest_testconfig import config as py_config
from resources.datavolume import ImportFromHttpDataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim


QCOW_IMG = 'cirros-qcow2.img'
TAR_IMG = 'cirros-qcow2.tar.gz'


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
