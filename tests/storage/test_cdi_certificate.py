# -*- coding: utf-8 -*-

"""
Automatic refresh of CDI certificates test suite
"""

import datetime
import logging
import time

import pytest
import tests.storage.utils as storage_utils
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.resource import ResourceEditor
from resources.secret import Secret
from resources.utils import TimeoutSampler
from utilities import console
from utilities.infra import Images
from utilities.storage import create_dv, get_images_external_http_server
from utilities.virt import VirtualMachineForTests, wait_for_console


LOGGER = logging.getLogger(__name__)
RFC3339_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_QCOW2_IMG_PATH = f"/tmp/{Images.Cdi.QCOW2_IMG}"


CDI_SECRETS = [
    "cdi-apiserver-server-cert",
    "cdi-apiserver-signer",
    "cdi-uploadproxy-server-cert",
    "cdi-uploadproxy-signer",
    "cdi-uploadserver-client-cert",
    "cdi-uploadserver-client-signer",
    "cdi-uploadserver-signer",
]


@pytest.fixture(scope="module")
def secrets(default_client):
    return Secret.get(dyn_client=default_client, namespace=py_config["hco_namespace"])


@pytest.fixture()
def valid_cdi_certificates(secrets):
    """
    Check whether all CDI certificates are valid.
    The cert time abstracted from CDI respective Secret annotations are like:
    auth.openshift.io/certificate-not-after: "2020-04-24T04:02:12Z"
    auth.openshift.io/certificate-not-before: "2020-04-22T04:02:11Z"
    """
    LOGGER.debug("Use 'valid_cdi_certificates' fixture...")
    for secret in secrets:
        for cdi_secret in CDI_SECRETS:
            if secret.name == cdi_secret:
                LOGGER.info(f"Checking {cdi_secret}...")

                start = secret.certificate_not_before
                start_timestamp = time.mktime(time.strptime(start, RFC3339_FORMAT))

                end = secret.certificate_not_after
                end_timestamp = time.mktime(time.strptime(end, RFC3339_FORMAT))

                current_time = datetime.datetime.now().strftime(RFC3339_FORMAT)
                current_timestamp = time.mktime(
                    time.strptime(current_time, RFC3339_FORMAT)
                )
                assert (
                    start_timestamp <= current_timestamp <= end_timestamp
                ), f"Certificate of {cdi_secret} expired"


@pytest.fixture()
def refresh_cdi_certificates(secrets):
    """
    Update the secret annotation "auth.openshift.io/certificate-not-after" to be equal to
    "auth.openshift.io/certificate-not-before" will trigger the cert renewal.
    This fixture refresh all CDI certificates.
    """
    LOGGER.debug("Use 'refresh_cdi_certificates' fixture...")
    for secret in secrets:
        for cdi_secret in CDI_SECRETS:
            if secret.name == cdi_secret:
                new_end = secret.certificate_not_before
                res = ResourceEditor(
                    {
                        secret: {
                            "metadata": {
                                "annotations": {
                                    "auth.openshift.io/certificate-not-after": f"{new_end}"
                                }
                            }
                        }
                    }
                )
                LOGGER.info(f"Wait for Secret {secret.name} to be updated")
                res.update()
                for sample in TimeoutSampler(
                    timeout=20,
                    sleep=10,
                    func=lambda: secret.certificate_not_before
                    != secret.certificate_not_after,
                ):
                    if sample:
                        break


@pytest.mark.polarion("CNV-3686")
def test_dv_delete_from_vm(valid_cdi_certificates, namespace):
    """
    Check that create VM with dataVolumeTemplates, once DV is deleted, the owner VM will create one.
    This will trigger the import process so that cert code will be exercised one more time.
    """
    dv = DataVolume(namespace=namespace.name, name="cnv-3686-dv")
    with VirtualMachineForTests(
        name="cnv-3686-vm",
        namespace=namespace.name,
        data_volume_template={
            "metadata": {"name": f"{dv.name}"},
            "spec": {
                "pvc": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": "1Gi"}},
                },
                "source": {
                    "http": {
                        "url": f"{get_images_external_http_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
                    }
                },
            },
        },
        dv=dv,
    ) as vm:
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=120)
        dv.delete()
        # DV re-creation is triggered by VM
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED)
        vm.start(wait=True)
        vm.vmi.wait_until_running(timeout=120)
        wait_for_console(vm=vm, console_impl=console.Cirros)


@pytest.mark.polarion("CNV-3667")
def test_upload_after_certs_renewal(
    refresh_cdi_certificates, download_image, namespace, storage_class_matrix__class__
):
    """
    Check that CDI can do upload operation after certs get refreshed
    """
    dv_name = "cnv-3667"
    res, out = storage_utils.virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size="1Gi",
        image_path=LOCAL_QCOW2_IMG_PATH,
        storage_class=[*storage_class_matrix__class__][0],
        insecure=True,
    )
    LOGGER.info(out)
    assert res
    assert "Processing completed successfully" in out
    dv = DataVolume(namespace=namespace.name, name=dv_name)
    dv.wait(timeout=60)
    with storage_utils.create_vm_from_dv(dv=dv, start=True) as vm:
        wait_for_console(vm=vm, console_impl=console.Cirros)


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": "1Gi",
                "wait": True,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-3678")
def test_import_clone_after_certs_renewal(
    refresh_cdi_certificates,
    data_volume_multi_storage_scope_class,
    namespace,
    storage_class_matrix__class__,
):
    """
    Check that CDI can do import and clone operation after certs get refreshed
    """
    storage_class = [*storage_class_matrix__class__][0]
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_class.size,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__class__[storage_class]["volume_mode"],
    ) as cdv:
        cdv.wait(timeout=180)
        with storage_utils.create_vm_from_dv(dv=cdv, start=True) as vm:
            wait_for_console(vm=vm, console_impl=console.Cirros)
