# -*- coding: utf-8 -*-

""" CDIConfig tests """
import logging

import pytest
from ocp_resources.configmap import ConfigMap
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import ResourceEditor
from ocp_resources.route import Route
from ocp_resources.storage_class import StorageClass
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from pytest_testconfig import config as py_config

import utilities.storage
from tests.storage import utils
from utilities.infra import Images, get_cert
from utilities.storage import (
    cdi_feature_gate_list_with_added_feature,
    check_cdi_feature_gate_enabled,
    downloaded_image,
    get_images_server_url,
)


pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)

STORAGE_WORKLOADS_DICT = {
    "limits": {"cpu": "505m", "memory": "2Gi"},
    "requests": {"cpu": "252m", "memory": "1Gi"},
}
NON_EXISTANT_SCRATCH_SC_DICT = {"scratchSpaceStorageClass": "NonExistantSC"}
INSECURE_REGISTRIES_LIST = ["added-private-registry:5000"]


def cdiconfig_update(
    source,
    hco_cr,
    cdiconfig,
    storage_class_type,
    storage_ns_name,
    dv_name,
    client,
    volume_mode=py_config["default_volume_mode"],
    access_mode=py_config["default_access_mode"],
    images_https_server_name="",
    run_vm=False,
    tmpdir=None,
):
    with ResourceEditor(
        patches={hco_cr: {"spec": {"scratchSpaceStorageClass": storage_class_type}}}
    ):
        samples = TimeoutSampler(
            wait_timeout=30,
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
                            access_mode=access_mode,
                            storage_ns_name=storage_ns_name,
                        ) as dv:
                            dv.wait()
                            with utils.create_vm_from_dv(dv=dv) as vm_dv:
                                utils.check_disk_count_in_vm(vm=vm_dv)
                                break
                    elif source == "upload":
                        local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
                        remote_name = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
                        downloaded_image(remote_name=remote_name, local_name=local_name)
                        with utils.upload_image_to_dv(
                            dv_name=dv_name,
                            volume_mode=volume_mode,
                            storage_ns_name=storage_ns_name,
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
    skip_test_if_no_hpp_sc,
    tmpdir,
    hyperconverged_resource_scope_module,
    cdi_config,
    namespace,
    unprivileged_client,
):
    cdiconfig_update(
        source="upload",
        hco_cr=hyperconverged_resource_scope_module,
        cdiconfig=cdi_config,
        dv_name="cnv-2451",
        storage_class_type=StorageClass.Types.HOSTPATH,
        images_https_server_name=get_images_server_url(schema="https"),
        storage_ns_name=namespace.name,
        volume_mode=DataVolume.VolumeMode.FILE,
        access_mode=DataVolume.AccessMode.RWO,
        run_vm=True,
        tmpdir=tmpdir,
        client=unprivileged_client,
    )


@pytest.mark.polarion("CNV-2478")
def test_cdiconfig_scratchspace_fs_import_to_block(
    skip_test_if_no_hpp_sc,
    hyperconverged_resource_scope_module,
    cdi_config,
    namespace,
    unprivileged_client,
):
    cdiconfig_update(
        source="http",
        hco_cr=hyperconverged_resource_scope_module,
        cdiconfig=cdi_config,
        dv_name="cnv-2478",
        storage_class_type=StorageClass.Types.HOSTPATH,
        storage_ns_name=namespace.name,
        volume_mode=DataVolume.VolumeMode.FILE,
        access_mode=DataVolume.AccessMode.RWO,
        images_https_server_name=get_images_server_url(schema="https"),
        run_vm=True,
        client=unprivileged_client,
    )


@pytest.mark.polarion("CNV-2214")
def test_cdiconfig_status_scratchspace_update_with_spec(
    skip_test_if_no_hpp_sc,
    hyperconverged_resource_scope_module,
    cdi_config,
    namespace,
    unprivileged_client,
):
    cdiconfig_update(
        source="http",
        hco_cr=hyperconverged_resource_scope_module,
        cdiconfig=cdi_config,
        dv_name="cnv-2214",
        storage_class_type=StorageClass.Types.HOSTPATH,
        storage_ns_name=namespace.name,
        volume_mode=DataVolume.VolumeMode.FILE,
        access_mode=DataVolume.AccessMode.RWO,
        client=unprivileged_client,
    )


@pytest.mark.polarion("CNV-2440")
def test_cdiconfig_scratch_space_not_default(
    skip_test_if_no_hpp_sc,
    hyperconverged_resource_scope_module,
    cdi_config,
    namespace,
    unprivileged_client,
):
    cdiconfig_update(
        source="http",
        hco_cr=hyperconverged_resource_scope_module,
        cdiconfig=cdi_config,
        dv_name="cnv-2440",
        storage_class_type=StorageClass.Types.HOSTPATH,
        images_https_server_name=get_images_server_url(schema="https"),
        storage_ns_name=namespace.name,
        run_vm=True,
        volume_mode=DataVolume.VolumeMode.FILE,
        access_mode=DataVolume.AccessMode.RWO,
        client=unprivileged_client,
    )


@pytest.fixture()
def skip_if_scratch_space_specified(cdi_config):
    if cdi_config.scratch_space_storage_class_from_spec:
        pytest.skip(
            msg="Skip test because cdiconfig.spec.scratchSpaceStorageClass is specified"
        )


@pytest.mark.polarion("CNV-2412")
def test_cdi_config_scratch_space_value_is_default(
    skip_if_scratch_space_specified,
    pyconfig_updated_default_sc,
    cdi_config,
):
    assert (
        cdi_config.scratch_space_storage_class_from_status
        == pyconfig_updated_default_sc.name
    )


@pytest.mark.polarion("CNV-2208")
def test_cdi_config_exists(skip_not_openshift, cdi_config, upload_proxy_route):
    assert cdi_config.upload_proxy_url == upload_proxy_route.host


@pytest.mark.destructive
@pytest.mark.polarion("CNV-2209")
def test_different_route_for_upload_proxy(
    skip_not_openshift, hco_namespace, cdi_config, uploadproxy_route_deleted
):
    with Route(
        namespace=hco_namespace.name,
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
    skip_test_if_no_hpp_sc,
    skip_test_if_no_ocs_sc,
    hpp_storage_class,
    namespace,
    pyconfig_updated_default_sc,
    cdi_config,
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
            pyconfig_updated_default_sc: _get_update_dict(
                default=False,
                storage_class=pyconfig_updated_default_sc.name,
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
                images_https_server=get_images_server_url(schema="https"),
                file_name=Images.Cirros.QCOW2_IMG,
            )
            with ConfigMap(
                name="https-cert-configmap",
                namespace=namespace.name,
                data={"tlsregistry.crt": get_cert(server_type="https_cert")},
            ) as configmap:
                with utilities.storage.create_dv(
                    source="http",
                    dv_name="import-cdiconfig-scratch-space-not-default",
                    namespace=configmap.namespace,
                    url=url,
                    storage_class=StorageClass.Types.CEPH_RBD,
                    volume_mode=DataVolume.VolumeMode.BLOCK,
                    cert_configmap=configmap.name,
                ) as dv:
                    dv.wait()
                    with utils.create_vm_from_dv(dv=dv) as vm_dv:
                        utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.polarion("CNV-5999")
def test_cdi_spec_reconciled_by_hco(cdi, namespace):
    """
    Test that added feature gate on the CDI CR does not persist
    (HCO Should reconcile back changes on the CDI CR)
    """
    non_existant_feature = "ExtraNonExistantFeature"
    with ResourceEditor(
        patches={
            cdi: {
                "spec": {
                    "config": {
                        "featureGates": cdi_feature_gate_list_with_added_feature(
                            feature=non_existant_feature
                        )
                    }
                }
            }
        }
    ):
        with pytest.raises(TimeoutExpiredError):
            for sample in TimeoutSampler(
                wait_timeout=20,
                sleep=1,
                func=lambda: check_cdi_feature_gate_enabled(
                    feature=non_existant_feature
                ),
            ):
                if sample:
                    LOGGER.error("Changes to CDI Spec should be reconciled by HCO")
                    break


@pytest.mark.parametrize(
    ("hco_updated_spec_stanza", "expected_in_cdi_config_from_cr"),
    [
        pytest.param(
            {"resourceRequirements": {"storageWorkloads": STORAGE_WORKLOADS_DICT}},
            {"podResourceRequirements": STORAGE_WORKLOADS_DICT},
            marks=(pytest.mark.polarion("CNV-6000")),
            id="test_storage_workloads_in_hco_propagated_to_cdi_cr",
        ),
        pytest.param(
            NON_EXISTANT_SCRATCH_SC_DICT,
            NON_EXISTANT_SCRATCH_SC_DICT,
            marks=(pytest.mark.polarion("CNV-6001")),
            id="test_scratch_sc_in_hco_propagated_to_cdi_cr",
        ),
        pytest.param(
            {"storageImport": {"insecureRegistries": INSECURE_REGISTRIES_LIST}},
            {"insecureRegistries": INSECURE_REGISTRIES_LIST},
            marks=(pytest.mark.polarion("CNV-6092")),
            id="test_insecure_registries_in_hco_propagated_to_cdi_cr",
        ),
    ],
)
def test_cdi_tunables_in_hco_propagated_to_cr(
    hyperconverged_resource_scope_module,
    cdi,
    namespace,
    expected_in_cdi_config_from_cr,
    hco_updated_spec_stanza,
):
    """
    Test that the exposed CDI-related tunables in HCO are propagated to the CDI CR
    """
    initial_cdi_config_from_cr = cdi.instance.to_dict()["spec"]["config"]

    def _verify_propagation():
        current_cdi_config_from_cr = cdi.instance.to_dict()["spec"]["config"]
        return {
            **initial_cdi_config_from_cr,
            **expected_in_cdi_config_from_cr,
        } == current_cdi_config_from_cr

    samples = TimeoutSampler(
        wait_timeout=20,
        sleep=1,
        func=_verify_propagation,
    )

    with ResourceEditor(
        patches={
            hyperconverged_resource_scope_module: {"spec": hco_updated_spec_stanza}
        }
    ):
        for sample in samples:
            if sample:
                break

    LOGGER.info("Check values revert back to original")
    for sample in samples:
        if not sample:
            break