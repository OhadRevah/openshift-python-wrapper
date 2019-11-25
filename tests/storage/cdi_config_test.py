# -*- coding: utf-8 -*-

""" CDIConfig tests """
import logging

import pytest
from resources.configmap import ConfigMap
from resources.datavolume import DataVolume
from resources.route import Route
from resources.storage_class import StorageClass
from resources.utils import TimeoutSampler
from tests.storage import utils
from utilities.infra import Images, get_cert


LOGGER = logging.getLogger(__name__)


@pytest.mark.polarion("CNV-2478")
def test_cdiconfig_scratchspace_fs_import_to_block(
    skip_no_local_storage_class, cdi_config, storage_ns, images_https_server
):
    cdiconfig_spec = cdi_config.instance.to_dict()["spec"]
    cdiconfig_status_scratch_space = cdi_config.scratch_space_storage_class_from_status
    cdiconfig_update(
        cdi_config,
        StorageClass.Types.LOCAL,
        cdiconfig_spec,
        cdiconfig_status_scratch_space,
        images_https_server,
        storage_ns.name,
        run_vm=True,
        volume_mode="Block",
    )


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
                source_type="http",
                dv_name="import-cdiconfig-scratch-space-not-default",
                namespace=configmap.namespace,
                url=url,
                cert_configmap=configmap.name,
                content_type=DataVolume.ContentType.KUBEVIRT,
                size="5Gi",
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


def cdiconfig_update(
    cdiconfig,
    storage_class_type,
    cdiconfig_spec,
    cdiconfig_status_scratch_space,
    images_https_server_name="",
    storage_ns_name="",
    run_vm=False,
    volume_mode=None,
):
    try:
        cdiconfig.update(
            resource_dict={
                "spec": {"scratchSpaceStorageClass": storage_class_type},
                "metadata": {"name": cdiconfig.name},
            }
        )
        samples = TimeoutSampler(
            timeout=30,
            sleep=1,
            func=lambda: cdiconfig.scratch_space_storage_class_from_status
            == storage_class_type,
        )
        for sample in samples:
            if sample:
                if run_vm:
                    url = utils.get_file_url_https_server(
                        images_https_server_name, Images.Cirros.QCOW2_IMG
                    )
                    with ConfigMap(
                        name="https-cert-configmap",
                        namespace=storage_ns_name,
                        data=get_cert("https_cert"),
                    ) as configmap:
                        with utils.create_dv(
                            source_type="http",
                            dv_name="import-cdiconfig-scratch-space-not-default",
                            namespace=configmap.namespace,
                            url=url,
                            cert_configmap=configmap.name,
                            content_type=DataVolume.ContentType.KUBEVIRT,
                            size="5Gi",
                            volume_mode=volume_mode,
                        ) as dv:
                            dv.wait()
                            with utils.create_vm_from_dv(dv) as vm_dv:
                                utils.check_disk_count_in_vm(vm_dv)
                                break
                break
    finally:
        cdiconfig.update(
            resource_dict={"spec": "", "metadata": {"name": cdiconfig.name}}
        )
        cdiconfig.update(
            resource_dict={"spec": cdiconfig_spec, "metadata": {"name": cdiconfig.name}}
        )
        samples = TimeoutSampler(
            timeout=10,
            sleep=1,
            func=lambda: cdiconfig.scratch_space_storage_class_from_status
            == cdiconfig_status_scratch_space,
        )
        for sample in samples:
            if sample:
                return


@pytest.mark.polarion("CNV-2214")
def test_cdiconfig_status_scratchspace_update_with_spec(cdi_config):
    cdiconfig_spec = cdi_config.instance.to_dict()["spec"]
    cdiconfig_status_scratch_space = cdi_config.scratch_space_storage_class_from_status
    cdiconfig_update(
        cdi_config,
        StorageClass.Types.LOCAL,
        cdiconfig_spec,
        cdiconfig_status_scratch_space,
    )


@pytest.mark.polarion("CNV-2440")
def test_cdiconfig_scratch_space_not_default(
    skip_no_local_storage_class, cdi_config, storage_ns, images_https_server
):
    cdiconfig_spec = cdi_config.instance.to_dict()["spec"]
    cdiconfig_status_scratch_space = cdi_config.scratch_space_storage_class_from_status
    cdiconfig_update(
        cdi_config,
        StorageClass.Types.LOCAL,
        cdiconfig_spec,
        cdiconfig_status_scratch_space,
        images_https_server,
        storage_ns.name,
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
