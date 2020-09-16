# -*- coding: utf-8 -*-
import logging
import multiprocessing

import pytest
import utilities.storage
from kubernetes.client.rest import ApiException
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.datavolume import DataVolume
from resources.resource import ResourceEditor
from tests.storage import utils
from tests.storage.cdi_import.conftest import wait_for_importer_container_message
from tests.storage.utils import get_importer_pod
from utilities.infra import BUG_STATUS_CLOSED, ErrorMsg, get_cert
from utilities.virt import VirtualMachineForTests


LOGGER = logging.getLogger(__name__)
DOCKERHUB_IMAGE = "docker://kubevirt/cirros-registry-disk-demo"
QUAY_IMAGE = "docker://quay.io/kubevirt/cirros-registry-disk-demo"
PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE = "cirros-registry-disk-demo:latest"
PRIVATE_REGISTRY_CIRROS_RAW_IMAGE = "cirros.raw:latest"
PRIVATE_REGISTRY_CIRROS_QCOW2_IMAGE = "cirros.qcow2:latest"
REGISTRY_TLS_SELF_SIGNED_SERVER = py_config[py_config["region"]]["registry_server"]


@pytest.fixture()
def disable_tls_registry(configmap_with_cert):
    """
    To disable TLS security for a registry
    """
    LOGGER.debug("Use 'disable_tls_registry' fixture...")
    cdi_insecure_registries = ConfigMap(
        name="cdi-insecure-registries", namespace=py_config["hco_namespace"]
    )
    ResourceEditor(
        {
            cdi_insecure_registries: {
                "data": {
                    py_config[py_config["region"]][
                        "registry_cert"
                    ]: f"{REGISTRY_TLS_SELF_SIGNED_SERVER}:8443",
                }
            }
        }
    ).update()


@pytest.fixture()
def configmap_with_cert(namespace):
    LOGGER.debug("Use 'configmap_with_cert' fixture...")
    with ConfigMap(
        name="registry-cm-cert",
        namespace=namespace.name,
        data={
            py_config[py_config["region"]]["registry_cert"]: get_cert(
                server_type="registry_cert"
            )
        },
    ) as configmap:
        yield configmap


@pytest.fixture()
def update_configmap_with_cert(request, configmap_with_cert):
    cert_name = py_config[py_config["region"]]["registry_cert"]
    LOGGER.debug("Use 'update_configmap_with_cert' fixture...")
    injected_content = request.param["injected_content"]
    ResourceEditor(
        {
            configmap_with_cert: {
                "data": {
                    cert_name: f"{configmap_with_cert.data[cert_name][:50]}{injected_content}"
                    f"{configmap_with_cert.data[cert_name][50:]}"
                }
            }
        }
    ).update()


@pytest.mark.parametrize(
    "file_name",
    [
        pytest.param(
            PRIVATE_REGISTRY_CIRROS_RAW_IMAGE,
            marks=(pytest.mark.polarion("CNV-2343")),
            id="import_cirros_raw",
        ),
        pytest.param(
            PRIVATE_REGISTRY_CIRROS_QCOW2_IMAGE,
            marks=(pytest.mark.polarion("CNV-2341")),
            id="import_cirros_qcow2_image",
        ),
    ],
)
def test_private_registry_cirros(
    skip_upstream,
    namespace,
    images_private_registry_server,
    registry_config_map,
    file_name,
    storage_class_matrix__function__,
):
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-private-registry-cirros-image",
        namespace=namespace.name,
        url=f"{images_private_registry_server}:8443/{file_name}",
        cert_configmap=registry_config_map.name,
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv=dv) as vm_dv:
            utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.parametrize(
    ("dv_name", "url", "error_msg"),
    [
        pytest.param(
            "cnv-2198",
            "docker://docker.io/cirros",
            ErrorMsg.DISK_IMAGE_IN_CONTAINER_NOT_FOUND,
            marks=(pytest.mark.polarion("CNV-2198")),
            id="image-registry-not-conform-registrydisk",
        ),
        pytest.param(
            "cnv-2340",
            "docker://quay.io/openshift-cnv/qe-cnv-tests-registry-fedora29-qcow2-rootdir",
            ErrorMsg.NOT_EXIST_IN_IMAGE_DIR,
            marks=(pytest.mark.polarion("CNV-2340")),
            id="import-registry-fedora29-qcow-rootdir",
        ),
    ],
)
def test_disk_image_not_conform_to_registy_disk(
    admin_client, dv_name, url, error_msg, namespace, storage_class_matrix__function__
):
    with utilities.storage.create_dv(
        source="registry",
        dv_name=dv_name,
        namespace=namespace.name,
        url=url,
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=300,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        importer_pod = get_importer_pod(dyn_client=admin_client, namespace=dv.namespace)
        wait_for_importer_container_message(
            importer_pod=importer_pod, msg=error_msg,
        )


@pytest.mark.polarion("CNV-2028")
def test_public_registry_multiple_data_volume(
    namespace, storage_class_matrix__function__
):
    dvs = []
    vms = []
    dvs_processes = []
    vms_processes = []
    try:
        for dv in ("dv1", "dv2", "dv3"):
            rdv = DataVolume(
                source="registry",
                name=f"import-registry-dockerhub-{dv}",
                namespace=namespace.name,
                url=DOCKERHUB_IMAGE,
                size="5Gi",
                content_type=DataVolume.ContentType.KUBEVIRT,
                **utils.storage_params(
                    storage_class_matrix=storage_class_matrix__function__
                ),
            )

            dv_process = multiprocessing.Process(target=rdv.create)
            dv_process.start()
            dvs_processes.append(dv_process)
            dvs.append(rdv)

        for dvp in dvs_processes:
            dvp.join()

        for dv in dvs:
            dv.wait()

        for vm in [vm for vm in dvs]:
            rvm = VirtualMachineForTests(name=vm.name, namespace=namespace.name, dv=vm)
            rvm.create(wait=True)
            vms.append(rvm)

        for vm in vms:
            vm_process = multiprocessing.Process(target=vm.start)
            vm_process.start()
            vms_processes.append(vm_process)

        for vmp in vms_processes:
            vmp.join()

        for vm in vms:
            vm.vmi.wait_until_running()
            utils.check_disk_count_in_vm(vm=vm)
    finally:
        for rcs in vms + dvs:
            rcs.delete(wait=True)


@pytest.mark.polarion("CNV-2183")
def test_private_registry_insecured_configmap(
    skip_upstream,
    namespace,
    images_private_registry_server,
    storage_class_matrix__function__,
):
    server = images_private_registry_server.replace("docker://", "")
    cm = ConfigMap(
        namespace=py_config["hco_namespace"], name="cdi-insecure-registries", data=None
    )

    cm.update(
        resource_dict={
            "data": {"mykey": f"{server}:5000"},
            "metadata": {"name": "cdi-insecure-registries"},
        }
    )
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-private-insecured-registry",
        namespace=namespace.name,
        url=f"{images_private_registry_server}:5000/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv=dv) as vm_dv:
            utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.polarion("CNV-2182")
def test_private_registry_recover_after_missing_configmap(
    skip_upstream,
    namespace,
    images_private_registry_server,
    registry_config_map,
    storage_class_matrix__function__,
):
    # creating DV before configmap with certificate is created
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-private-registry-with-no-configmap",
        namespace=namespace.name,
        url=f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
        cert_configmap=registry_config_map.name,
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.IMPORT_SCHEDULED, timeout=300)
        dv.wait()
        with utils.create_vm_from_dv(dv=dv) as vm_dv:
            utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.polarion("CNV-2344")
def test_private_registry_with_untrusted_certificate(
    skip_upstream,
    admin_client,
    namespace,
    images_private_registry_server,
    registry_config_map,
    storage_class_matrix__function__,
):
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-private-registry-with-untrusted-certificate",
        namespace=namespace.name,
        url=f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
        cert_configmap=registry_config_map.name,
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv=dv) as vm_dv:
            utils.check_disk_count_in_vm(vm=vm_dv)

        # negative flow - remove certificate from configmap
        registry_config_map.update(
            resource_dict={
                "data": {"tlsregistry.crt": ""},
                "metadata": {"name": registry_config_map.name},
            }
        )
        with utilities.storage.create_dv(
            source="registry",
            dv_name="import-private-registry-no-certificate",
            namespace=namespace.name,
            url=f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
            cert_configmap=registry_config_map.name,
            content_type="",
            **utils.storage_params(
                storage_class_matrix=storage_class_matrix__function__
            ),
        ) as dv:
            dv.wait_for_status(status=DataVolume.Status.IMPORT_IN_PROGRESS, timeout=300)
            importer_pod = get_importer_pod(
                dyn_client=admin_client, namespace=dv.namespace
            )
            wait_for_importer_container_message(
                importer_pod=importer_pod, msg=ErrorMsg.EXIT_STATUS_1,
            )


@pytest.mark.parametrize(
    ("dv_name", "url", "cert_configmap", "content_type", "size"),
    [
        pytest.param(
            "import-registry-dockerhub-dv",
            DOCKERHUB_IMAGE,
            None,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2041")),
        ),
        pytest.param(
            "import-registry-dockerhub-no-content-type-dv",
            DOCKERHUB_IMAGE,
            None,
            None,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2195")),
        ),
        pytest.param(
            "import-registry-dockerhub-empty-content-type-dv",
            DOCKERHUB_IMAGE,
            None,
            "",
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2197")),
        ),
        pytest.param(
            "import-registry-quay-dv",
            QUAY_IMAGE,
            None,
            DataVolume.ContentType.KUBEVIRT,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2026")),
        ),
    ],
    ids=[
        "import-registry-dockerhub-dv",
        "import-registry-dockerhub-no-content-type-dv",
        "import-registry-dockerhub-empty-content-type-dv",
        "import-registry-quay-dv",
    ],
)
def test_public_registry_data_volume(
    namespace,
    dv_name,
    url,
    cert_configmap,
    content_type,
    size,
    storage_class_matrix__function__,
):
    with utilities.storage.create_dv(
        source="registry",
        dv_name=dv_name,
        namespace=namespace.name,
        url=url,
        cert_configmap=cert_configmap,
        content_type=content_type,
        size=size,
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv=dv) as vm_dv:
            utils.check_disk_count_in_vm(vm=vm_dv)


# The following test is to show after imports fails because low capacity storage,
# we can overcome by updaing to the right requested volume size and import successfully
@pytest.mark.polarion("CNV-2024")
def test_public_registry_data_volume_dockerhub_low_capacity(
    admin_client, namespace, storage_class_matrix__function__
):
    # negative flow - low capacity volume
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-registry-dockerhub-low-capacity-dv",
        namespace=namespace.name,
        url=DOCKERHUB_IMAGE,
        content_type="",
        size="16Mi",
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=300,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        importer_pod = get_importer_pod(dyn_client=admin_client, namespace=dv.namespace)
        wait_for_importer_container_message(
            importer_pod=importer_pod, msg=ErrorMsg.LARGER_PVC_REQUIRED,
        )

    # positive flow
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-registry-dockerhub-low-capacity-dv",
        namespace=namespace.name,
        url=DOCKERHUB_IMAGE,
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv=dv) as vm_dv:
            utils.check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.bugzilla(
    1725372, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.polarion("CNV-2150")
def test_public_registry_data_volume_dockerhub_archive(
    namespace, storage_class_matrix__function__
):
    with pytest.raises(
        ApiException, match=r".*ContentType must be kubevirt when Source is Registry.*"
    ):
        with utilities.storage.create_dv(
            source="registry",
            dv_name="import-registry-archive",
            namespace=namespace.name,
            url=DOCKERHUB_IMAGE,
            content_type=DataVolume.ContentType.ARCHIVE,
            **utils.storage_params(
                storage_class_matrix=storage_class_matrix__function__
            ),
        ):
            return


@pytest.mark.polarion("CNV-2347")
def test_fqdn_name(
    namespace,
    configmap_with_cert,
    disable_tls_registry,
    storage_class_matrix__function__,
):
    """
    Test that it does a full name string check in the insecure registry ConfigMap,
    not a partial check of just the prefix.
    """
    storage_class = [*storage_class_matrix__function__][0]
    with utilities.storage.create_dv(
        source="registry",
        dv_name=f"cnv-2347-{storage_class}",
        namespace=namespace.name,
        # Substring of the FQDN name
        url=f"{REGISTRY_TLS_SELF_SIGNED_SERVER[:22]}{REGISTRY_TLS_SELF_SIGNED_SERVER[30:]}:8443/"
        f"{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
        cert_configmap=configmap_with_cert.name,
        size="1Gi",
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        # Import fails because FQDN is verified from the registry certificate and a substring is not supported.
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.BOUND,
            status=DataVolume.Condition.Status.TRUE,
            timeout=60,
        )
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_SCHEDULED,
            timeout=300,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.RUNNING,
            status=DataVolume.Condition.Status.FALSE,
            timeout=300,
        )
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.READY,
            status=DataVolume.Condition.Status.FALSE,
            timeout=300,
        )


@pytest.mark.parametrize(
    ("dv_name", "update_configmap_with_cert"),
    [
        pytest.param(
            "cnv-2351",
            {"injected_content": "\0,^@%$!#$%~*()"},
            marks=(pytest.mark.polarion("CNV-2351")),
            id="invalid_control_characters_in_cert_configmap",
        ),
        pytest.param(
            "cnv-2352",
            {"injected_content": "0101010101010010010101001010"},
            marks=(pytest.mark.polarion("CNV-2352")),
            id="binary_string_in_cert_configmap",
        ),
    ],
    indirect=["update_configmap_with_cert"],
)
def test_inject_invalid_cert_to_configmap(
    admin_client,
    dv_name,
    configmap_with_cert,
    update_configmap_with_cert,
    namespace,
    images_private_registry_server,
    storage_class_matrix__function__,
):
    """
    Test that generate ConfigMap from cert file, then inject invalid content in the cert of ConfigMap, import will fail.
    """
    with utilities.storage.create_dv(
        source="registry",
        dv_name=dv_name,
        namespace=namespace.name,
        url=f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
        cert_configmap=configmap_with_cert.name,
        size="1Gi",
        **utils.storage_params(storage_class_matrix=storage_class_matrix__function__),
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.IMPORT_IN_PROGRESS, timeout=600)
        importer_pod = get_importer_pod(dyn_client=admin_client, namespace=dv.namespace)
        wait_for_importer_container_message(
            importer_pod=importer_pod, msg=ErrorMsg.EXIT_STATUS_1,
        )
