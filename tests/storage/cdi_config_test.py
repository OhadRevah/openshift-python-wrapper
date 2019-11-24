# -*- coding: utf-8 -*-

""" CDIConfig tests """
import logging

import pytest
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.datavolume import DataVolume
from resources.resource import ResourceEditor
from resources.route import Route
from resources.storage_class import StorageClass
from resources.utils import TimeoutSampler
from tests.storage import utils
from utilities.infra import Images, get_cert


LOGGER = logging.getLogger(__name__)


def cdiconfig_update(
    source,
    cdiconfig,
    storage_class_type,
    storage_ns_name,
    volume_mode=DataVolume.VolumeMode.FILE,
    images_https_server_name="",
    run_vm=False,
    tmpdir=None,
):
    with ResourceEditor(
        {cdiconfig: {"spec": {"scratchSpaceStorageClass": storage_class_type}}}
    ):
        samples = TimeoutSampler(
            timeout=30,
            sleep=1,
            func=lambda: cdiconfig.scratch_space_storage_class_from_status
            == storage_class_type,
        )
        for sample in samples:
            if sample:
                if run_vm:
                    if source == "http":
                        with utils.import_image_to_dv(
                            images_https_server_name, volume_mode, storage_ns_name,
                        ) as dv:
                            dv.wait()
                            with utils.create_vm_from_dv(dv) as vm_dv:
                                utils.check_disk_count_in_vm(vm_dv)
                                break
                    elif source == "upload":
                        with utils.upload_image_to_dv(
                            tmpdir, volume_mode, storage_ns_name,
                        ) as dv:
                            dv.wait()
                            with utils.create_vm_from_dv(dv=dv) as vm_dv:
                                utils.check_disk_count_in_vm(vm_dv)
                                break


@pytest.mark.polarion("CNV-2451")
def test_cdiconfig_scratchspace_fs_upload_to_block(
    tmpdir, skip_no_local_storage_class, cdi_config, storage_ns, images_https_server,
):
    cdiconfig_update(
        source="upload",
        cdiconfig=cdi_config,
        storage_class_type=StorageClass.Types.LOCAL,
        images_https_server_name=images_https_server,
        storage_ns_name=storage_ns.name,
        volume_mode=DataVolume.VolumeMode.BLOCK,
        run_vm=True,
        tmpdir=tmpdir,
    )


@pytest.mark.polarion("CNV-2478")
def test_cdiconfig_scratchspace_fs_import_to_block(
    skip_no_local_storage_class, cdi_config, storage_ns, images_https_server
):
    cdiconfig_update(
        source="http",
        cdiconfig=cdi_config,
        storage_class_type=StorageClass.Types.LOCAL,
        storage_ns_name=storage_ns.name,
        volume_mode=DataVolume.VolumeMode.BLOCK,
        images_https_server_name=images_https_server,
        run_vm=True,
    )


@pytest.mark.polarion("CNV-2214")
def test_cdiconfig_status_scratchspace_update_with_spec(cdi_config, storage_ns):
    cdiconfig_update(
        source="http",
        cdiconfig=cdi_config,
        storage_class_type=StorageClass.Types.LOCAL,
        storage_ns_name=storage_ns.name,
    )


@pytest.mark.polarion("CNV-2440")
def test_cdiconfig_scratch_space_not_default(
    skip_no_local_storage_class, cdi_config, storage_ns, images_https_server
):
    cdiconfig_update(
        source="http",
        cdiconfig=cdi_config,
        storage_class_type=StorageClass.Types.LOCAL,
        images_https_server_name=images_https_server,
        storage_ns_name=storage_ns.name,
        run_vm=True,
    )


@pytest.mark.polarion("CNV-2412")
def test_cdi_config_scratch_space_value_is_default(
    skip_no_default_sc, cdi_config, default_sc
):
    assert cdi_config.scratch_space_storage_class_from_status == default_sc.name


@pytest.mark.polarion("CNV-2208")
def test_cdi_config_exists(cdi_config, upload_proxy_route):
    assert cdi_config.upload_proxy_url == upload_proxy_route.host


@pytest.mark.polarion("CNV-2209")
def test_different_route_for_upload_proxy(
    cdi_config, storage_ns, uploadproxy_route_deleted
):
    with Route(
        namespace=storage_ns.name, name="my-route", service="cdi-uploadproxy"
    ) as new_route:
        cdi_config.wait_until_upload_url_changed(new_route.host)


@pytest.mark.polarion("CNV-2215")
def test_route_for_different_service(cdi_config, upload_proxy_route):
    with Route(
        namespace=upload_proxy_route.namespace, name="cdi-api", service="cdi-api"
    ) as cdi_api_route:
        assert cdi_config.upload_proxy_url != cdi_api_route.host
        assert cdi_config.upload_proxy_url == upload_proxy_route.host


@pytest.mark.polarion("CNV-2216")
def test_upload_proxy_url_overridden(
    cdi_config, storage_ns, cdi_config_upload_proxy_overridden
):
    with Route(
        namespace=storage_ns.name, name="my-route", service="cdi-uploadproxy"
    ) as new_route:
        assert cdi_config.upload_proxy_url != new_route.host


@pytest.mark.polarion("CNV-2441")
def test_cdiconfig_changing_storage_class_default(
    skip_no_local_storage_class,
    cdi_config,
    storage_ns,
    images_https_server,
    local_storage_class,
    default_sc,
):
    try:
        default_sc.update(
            resource_dict={
                "metadata": {
                    "annotations": {
                        "storageclass.kubernetes.io/is-default-class": "false"
                    },
                    "name": StorageClass.Types.ROOK,
                },
            }
        )

        local_storage_class.update(
            resource_dict={
                "metadata": {
                    "annotations": {
                        "storageclass.kubernetes.io/is-default-class": "true"
                    },
                    "name": StorageClass.Types.LOCAL,
                },
            }
        )
        url = utils.get_file_url_https_server(
            images_https_server, Images.Cirros.QCOW2_IMG
        )
        with ConfigMap(
            name="https-cert-configmap",
            namespace=storage_ns.name,
            data=get_cert("https_cert"),
        ) as configmap:
            with utils.create_dv(
                source="http",
                dv_name="import-cdiconfig-scratch-space-not-default",
                namespace=configmap.namespace,
                url=url,
                storage_class=py_config["default_storage_class"],
                cert_configmap=configmap.name,
            ) as dv:
                dv.wait()
                with utils.create_vm_from_dv(dv) as vm_dv:
                    utils.check_disk_count_in_vm(vm_dv)

    finally:
        local_storage_class.update(
            resource_dict={
                "metadata": {
                    "annotations": {
                        "storageclass.kubernetes.io/is-default-class": "false"
                    },
                    "name": StorageClass.Types.LOCAL,
                },
            }
        )
        default_sc.update(
            resource_dict={
                "metadata": {
                    "annotations": {
                        "storageclass.kubernetes.io/is-default-class": "true"
                    },
                    "name": StorageClass.Types.ROOK,
                },
            }
        )
