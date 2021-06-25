# -*- coding: utf-8 -*-

"""
Automatic refresh of CDI certificates test suite
"""

import datetime
import logging
import subprocess
import time

import pytest
from ocp_resources.configmap import ConfigMap
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import ResourceEditor
from ocp_resources.secret import Secret
from ocp_resources.utils import TimeoutSampler

import tests.storage.utils as storage_utils
from utilities.constants import OS_FLAVOR_CIRROS, TIMEOUT_3MIN, TIMEOUT_10MIN, Images
from utilities.storage import (
    create_dummy_first_consumer_pod,
    create_dv,
    get_images_server_url,
    sc_is_hpp_with_immediate_volume_binding,
    sc_volume_binding_mode_is_wffc,
    virtctl_upload_dv,
)
from utilities.virt import VirtualMachineForTests, running_vm


pytestmark = pytest.mark.post_upgrade


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


def x509_cert_is_valid(cert, seconds):
    """
    Checks if the certificate expires within the next {seconds} seconds.
    """
    try:
        subprocess.check_output(
            f"openssl x509 -checkend {seconds}",
            input=cert,
            shell=True,
            universal_newlines=True,
        )
    except subprocess.CalledProcessError as e:
        if "Certificate will expire" in e.output:
            return False
        raise e
    return True


@pytest.fixture(scope="module")
def secrets(admin_client, hco_namespace):
    return Secret.get(dyn_client=admin_client, namespace=hco_namespace.name)


@pytest.fixture()
def valid_cdi_certificates(secrets):
    """
    Check whether all CDI certificates are valid.
    The cert time abstracted from CDI respective Secret annotations are like:
    auth.openshift.io/certificate-not-after: "2020-04-24T04:02:12Z"
    auth.openshift.io/certificate-not-before: "2020-04-22T04:02:11Z"
    """
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
def valid_aggregated_api_client_cert():
    """
    Performing the following steps will determine whether the extension-apiserver-authentication cert
    has been renewed within the valid time frame
    """
    kube_system_ns = "kube-system"
    aggregated_cm = "extension-apiserver-authentication"
    cert_end = "-----END CERTIFICATE-----\n"
    cm_data = ConfigMap(namespace=kube_system_ns, name=aggregated_cm).instance["data"]
    for cert_attr, cert_data in cm_data.items():
        if "ca-file" not in cert_attr:
            continue
        # Multiple certs can exist in one dict value (client-ca-file, for example)
        cert_list = [
            cert + cert_end
            for cert in cert_data.split(cert_end)
            if cert not in ("", cert_end)
        ]
        for cert in cert_list:
            # Check if certificate won't expire in next 10 minutes
            if not x509_cert_is_valid(cert=cert, seconds=TIMEOUT_10MIN):
                raise pytest.fail(
                    f"Certificate located in: {cert_attr} expires in less than 10 minutes"
                )


@pytest.fixture()
def refresh_cdi_certificates(secrets):
    """
    Update the secret annotation "auth.openshift.io/certificate-not-after" to be equal to
    "auth.openshift.io/certificate-not-before" will trigger the cert renewal.
    This fixture refresh all CDI certificates.
    """
    for secret in secrets:
        for cdi_secret in CDI_SECRETS:
            if secret.name == cdi_secret:
                new_end = secret.certificate_not_before
                res = ResourceEditor(
                    patches={
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
                    wait_timeout=20,
                    sleep=10,
                    func=lambda: secret.certificate_not_before
                    != secret.certificate_not_after,
                ):
                    if sample:
                        break


@pytest.mark.polarion("CNV-3686")
def test_dv_delete_from_vm(
    valid_cdi_certificates, namespace, storage_class_matrix__module__, worker_node1
):
    """
    Check that create VM with dataVolumeTemplates, once DV is deleted, the owner VM will create one.
    This will trigger the import process so that cert code will be exercised one more time.
    """
    dv = DataVolume(namespace=namespace.name, name="cnv-3686-dv")
    storage_class = [*storage_class_matrix__module__][0]
    dv_template = {
        "metadata": {
            "name": f"{dv.name}",
        },
        "spec": {
            "pvc": {
                "storageClassName": storage_class,
                "volumeMode": storage_class_matrix__module__[storage_class][
                    "volume_mode"
                ],
                "accessModes": [
                    storage_class_matrix__module__[storage_class]["access_mode"]
                ],
                "resources": {"requests": {"storage": "1Gi"}},
            },
            "source": {
                "http": {
                    "url": f"{get_images_server_url(schema='http')}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
                }
            },
        },
    }
    if sc_is_hpp_with_immediate_volume_binding(sc=storage_class):
        dv_template["metadata"]["annotations"] = {
            "kubevirt.io/provisionOnNode": worker_node1.name
        }
    with VirtualMachineForTests(
        name="cnv-3686-vm",
        namespace=namespace.name,
        os_flavor=OS_FLAVOR_CIRROS,
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
        data_volume_template=dv_template,
    ) as vm:
        if sc_volume_binding_mode_is_wffc(sc=storage_class):
            create_dummy_first_consumer_pod(dv=dv)
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=120)
        dv.delete()
        create_dummy_first_consumer_pod(dv=dv)
        # DV re-creation is triggered by VM
        running_vm(vm=vm, wait_for_interfaces=False)
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED)
        storage_utils.check_disk_count_in_vm(vm=vm)


@pytest.mark.polarion("CNV-3667")
def test_upload_after_certs_renewal(
    refresh_cdi_certificates,
    download_image,
    namespace,
    storage_class_matrix__module__,
):
    """
    Check that CDI can do upload operation after certs get refreshed
    """
    dv_name = "cnv-3667"
    with virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size="1Gi",
        image_path=LOCAL_QCOW2_IMG_PATH,
        storage_class=[*storage_class_matrix__module__][0],
        insecure=True,
    ) as res:
        status, out, _ = res
        LOGGER.info(out)
        assert status
        assert "Processing completed successfully" in out
        dv = DataVolume(namespace=namespace.name, name=dv_name)
        dv.wait(timeout=60)
        with storage_utils.create_vm_from_dv(dv=dv, start=True) as vm:
            storage_utils.check_disk_count_in_vm(vm=vm)


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_module",
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
    data_volume_multi_storage_scope_module,
    namespace,
):
    """
    Check that CDI can do import and clone operation after certs get refreshed
    """
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.name,
        storage_class=data_volume_multi_storage_scope_module.storage_class,
        volume_mode=data_volume_multi_storage_scope_module.volume_mode,
        access_modes=data_volume_multi_storage_scope_module.access_modes,
    ) as cdv:
        cdv.wait(timeout=TIMEOUT_3MIN)
        with storage_utils.create_vm_from_dv(dv=cdv, start=True) as vm:
            storage_utils.check_disk_count_in_vm(vm=vm)


@pytest.mark.polarion("CNV-3977")
def test_upload_after_validate_aggregated_api_cert(
    valid_aggregated_api_client_cert,
    namespace,
    storage_class_matrix__module__,
    download_image,
):
    """
    Check that upload is successful after verifying validity of aggregated api client certificate
    """
    dv_name = "cnv-3977"
    with virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size="1Gi",
        image_path=LOCAL_QCOW2_IMG_PATH,
        storage_class=[*storage_class_matrix__module__][0],
        insecure=True,
    ) as res:
        status, out, _ = res
        LOGGER.info(out)
        assert status
        assert "Processing completed successfully" in out
        dv = DataVolume(namespace=namespace.name, name=dv_name)
        dv.wait(timeout=60)
        with storage_utils.create_vm_from_dv(dv=dv, start=True) as vm:
            storage_utils.check_disk_count_in_vm(vm=vm)
