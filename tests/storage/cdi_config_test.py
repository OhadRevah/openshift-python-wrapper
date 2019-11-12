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
                server_type="http",
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


@pytest.mark.polarion("CNV-2440")
def test_cdiconfig_scratch_space_not_default(
    skip_no_local_storage_class, cdi_config, storage_ns, images_https_server, default_sc
):
    cdi_spec = cdi_config.instance.to_dict()["spec"]
    try:
        cdi_config.update(
            resource_dict={
                "spec": {"scratchSpaceStorageClass": StorageClass.Types.LOCAL},
                "metadata": {"name": cdi_config.name},
            }
        )
        samples = TimeoutSampler(
            timeout=30,
            sleep=1,
            func=lambda: cdi_config.scratch_space_storage_class_from_status
            == StorageClass.Types.LOCAL,
        )
        for sample in samples:
            if sample:
                url = utils.get_file_url_https_server(
                    images_https_server, Images.Cirros.QCOW2_IMG
                )
                with ConfigMap(
                    name="https-cert-configmap",
                    namespace=storage_ns.name,
                    data=get_cert("https_cert"),
                ) as configmap:
                    with utils.create_dv(
                        server_type="http",
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
                            break
    finally:
        cdi_config.update(
            resource_dict={"spec": "", "metadata": {"name": cdi_config.name}}
        )
        cdi_config.update(
            resource_dict={"spec": cdi_spec, "metadata": {"name": cdi_config.name}}
        )
        samples = TimeoutSampler(
            timeout=10,
            sleep=1,
            func=lambda: cdi_config.scratch_space_storage_class_from_status
            == default_sc.name,
        )
        for sample in samples:
            if sample:
                return


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
