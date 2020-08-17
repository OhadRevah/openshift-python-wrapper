# -*- coding: utf-8 -*-

""" CDIConfig tests """
import logging

import pytest
import utilities.storage
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.datavolume import DataVolume
from resources.resource import ResourceEditor
from resources.route import Route
from resources.storage_class import StorageClass
from resources.utils import TimeoutSampler
from tests.storage import utils
from utilities.infra import Images, get_cert
from utilities.storage import get_images_https_server


LOGGER = logging.getLogger(__name__)


def cdiconfig_update(
    source,
    cdiconfig,
    storage_class_type,
    storage_ns_name,
    dv_name,
    client,
    volume_mode=py_config["default_volume_mode"],
    images_https_server_name="",
    run_vm=False,
    tmpdir=None,
):
    with ResourceEditor(
        patches={cdiconfig: {"spec": {"scratchSpaceStorageClass": storage_class_type}}}
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
                            dv_name=dv_name,
                            images_https_server_name=images_https_server_name,
                            volume_mode=volume_mode,
                            storage_ns_name=storage_ns_name,
                        ) as dv:
                            dv.wait()
                            with utils.create_vm_from_dv(dv=dv) as vm_dv:
                                utils.check_disk_count_in_vm(vm=vm_dv)
                                break
                    elif source == "upload":
                        local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
                        remote_name = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
                        utils.downloaded_image(
                            remote_name=remote_name, local_name=local_name
                        )
                        with utils.upload_image_to_dv(
                            dv_name,
                            volume_mode,
                            storage_ns_name,
                            storage_class=storage_class_type,
                            client=client,
                        ) as dv:
                            utils.upload_token_request(
                                storage_ns_name, pvc_name=dv.pvc.name, data=local_name
                            )
                            dv.wait()
                            with utils.create_vm_from_dv(dv=dv) as vm_dv:
                                utils.check_disk_count_in_vm(vm_dv)
                                break
                break


@pytest.mark.polarion("CNV-2451")
def test_cdiconfig_scratchspace_fs_upload_to_block(
    skip_test_if_no_hpp_sc, tmpdir, cdi_config, namespace, unprivileged_client
):
    cdiconfig_update(
        source="upload",
        cdiconfig=cdi_config,
        dv_name="cnv-2451",
        storage_class_type=StorageClass.Types.HOSTPATH,
        images_https_server_name=get_images_https_server(),
        storage_ns_name=namespace.name,
        volume_mode=DataVolume.VolumeMode.FILE,
        run_vm=True,
        tmpdir=tmpdir,
        client=unprivileged_client,
    )


@pytest.mark.polarion("CNV-2478")
def test_cdiconfig_scratchspace_fs_import_to_block(
    skip_test_if_no_hpp_sc, cdi_config, namespace, unprivileged_client
):
    cdiconfig_update(
        source="http",
        cdiconfig=cdi_config,
        dv_name="cnv-2478",
        storage_class_type=StorageClass.Types.HOSTPATH,
        storage_ns_name=namespace.name,
        volume_mode=DataVolume.VolumeMode.FILE,
        images_https_server_name=get_images_https_server(),
        run_vm=True,
        client=unprivileged_client,
    )


@pytest.mark.polarion("CNV-2214")
def test_cdiconfig_status_scratchspace_update_with_spec(
    skip_test_if_no_hpp_sc, cdi_config, namespace, unprivileged_client
):
    cdiconfig_update(
        source="http",
        cdiconfig=cdi_config,
        dv_name="cnv-2214",
        storage_class_type=StorageClass.Types.HOSTPATH,
        storage_ns_name=namespace.name,
        volume_mode=DataVolume.VolumeMode.FILE,
        client=unprivileged_client,
    )


@pytest.mark.polarion("CNV-2440")
def test_cdiconfig_scratch_space_not_default(
    skip_test_if_no_hpp_sc, cdi_config, namespace, unprivileged_client
):
    cdiconfig_update(
        source="http",
        cdiconfig=cdi_config,
        dv_name="cnv-2440",
        storage_class_type=StorageClass.Types.HOSTPATH,
        images_https_server_name=get_images_https_server(),
        storage_ns_name=namespace.name,
        run_vm=True,
        volume_mode=DataVolume.VolumeMode.FILE,
        client=unprivileged_client,
    )


@pytest.fixture()
def skip_if_scratch_space_specified(cdi_config):
    LOGGER.debug("Use 'skip_if_scratch_space_specifie' fixture...")
    if cdi_config.scratch_space_storage_class_from_spec:
        pytest.skip(
            msg="Skip test because cdiconfig.spec.scratchSpaceStorageClass is specified"
        )


@pytest.mark.polarion("CNV-2412")
def test_cdi_config_scratch_space_value_is_default(
    skip_no_default_sc, skip_if_scratch_space_specified, cdi_config, default_sc
):
    assert cdi_config.scratch_space_storage_class_from_status == default_sc.name


@pytest.mark.polarion("CNV-2208")
def test_cdi_config_exists(skip_not_openshift, cdi_config, upload_proxy_route):
    assert cdi_config.upload_proxy_url == upload_proxy_route.host


@pytest.mark.destructive
@pytest.mark.polarion("CNV-2209")
def test_different_route_for_upload_proxy(
    skip_not_openshift, cdi_config, uploadproxy_route_deleted
):
    with Route(
        namespace=py_config["hco_namespace"],
        name="new-route-uploadproxy",
        service="cdi-uploadproxy",
    ) as new_route:
        cdi_config.wait_until_upload_url_changed(uploadproxy_url=new_route.host)


@pytest.mark.polarion("CNV-2215")
def test_route_for_different_service(
    skip_not_openshift, cdi_config, upload_proxy_route
):
    with Route(
        namespace=upload_proxy_route.namespace, name="cdi-api", service="cdi-api"
    ) as cdi_api_route:
        assert cdi_config.upload_proxy_url != cdi_api_route.host
        assert cdi_config.upload_proxy_url == upload_proxy_route.host


@pytest.mark.polarion("CNV-2216")
def test_upload_proxy_url_overridden(
    skip_not_openshift, cdi_config, namespace, cdi_config_upload_proxy_overridden
):
    with Route(
        namespace=namespace.name, name="my-route", service="cdi-uploadproxy"
    ) as new_route:
        assert cdi_config.upload_proxy_url != new_route.host


@pytest.mark.polarion("CNV-2441")
def test_cdiconfig_changing_storage_class_default(
    skip_test_if_no_hpp_sc, cdi_config, namespace, hpp_storage_class, default_sc,
):
    def _get_update_dict(default, storage_class):
        return {
            "metadata": {
                "annotations": {
                    "storageclass.kubernetes.io/is-default-class": str(default).lower()
                },
                "name": storage_class,
            },
        }

    with ResourceEditor(
        patches={
            default_sc: _get_update_dict(
                default=False, storage_class=StorageClass.Types.CEPH_RBD
            )
        }
    ):
        with ResourceEditor(
            patches={
                hpp_storage_class: _get_update_dict(
                    default=True, storage_class=StorageClass.Types.HOSTPATH
                )
            }
        ):
            url = utils.get_file_url_https_server(
                images_https_server=get_images_https_server(),
                file_name=Images.Cirros.QCOW2_IMG,
            )
            with ConfigMap(
                name="https-cert-configmap",
                namespace=namespace.name,
                data=get_cert(server_type="https_cert"),
            ) as configmap:
                with utilities.storage.create_dv(
                    source="http",
                    dv_name="import-cdiconfig-scratch-space-not-default",
                    namespace=configmap.namespace,
                    url=url,
                    storage_class=default_sc.name,
                    volume_mode=DataVolume.VolumeMode.FILE,
                    cert_configmap=configmap.name,
                ) as dv:
                    dv.wait()
                    with utils.create_vm_from_dv(dv=dv) as vm_dv:
                        utils.check_disk_count_in_vm(vm=vm_dv)
