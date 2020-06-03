# -*- coding: utf-8 -*-
import multiprocessing

import pytest
import utilities.storage
from kubernetes.client.rest import ApiException
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.datavolume import DataVolume
from tests.storage import utils
from tests.storage.cdi_import.conftest import wait_for_importer_container_message
from utilities.infra import BUG_STATUS_CLOSED, ErrorMsg
from utilities.virt import VirtualMachineForTests


DOCKERHUB_IMAGE = "docker://kubevirt/cirros-registry-disk-demo"
QUAY_IMAGE = "docker://quay.io/kubevirt/cirros-registry-disk-demo"
PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE = "cirros-registry-disk-demo:latest"
PRIVATE_REGISTRY_CIRROS_RAW_IMAGE = "cirros.raw:latest"
PRIVATE_REGISTRY_CIRROS_QCOW2_IMAGE = "cirros-qcow2.img:latest"


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
    storage_class = [*storage_class_matrix__function__][0]
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-private-registry-cirros-image",
        namespace=namespace.name,
        url=f"{images_private_registry_server}:8443/{file_name}",
        cert_configmap=registry_config_map.name,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__function__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv) as vm_dv:
            utils.check_disk_count_in_vm(vm_dv)


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
    dv_name, url, error_msg, namespace, storage_class_matrix__function__
):
    storage_class = [*storage_class_matrix__function__][0]
    with utilities.storage.create_dv(
        source="registry",
        dv_name=dv_name,
        namespace=namespace.name,
        url=url,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__function__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=300,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        wait_for_importer_container_message(
            importer_pod=dv.importer_pod, msg=error_msg,
        )


@pytest.mark.polarion("CNV-2028")
def test_public_registry_multiple_data_volume(
    namespace, storage_class_matrix__function__
):
    storage_class = [*storage_class_matrix__function__][0]
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
                storage_class=storage_class,
                volume_mode=storage_class_matrix__function__[storage_class][
                    "volume_mode"
                ],
                size="5Gi",
                content_type=DataVolume.ContentType.KUBEVIRT,
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
            utils.check_disk_count_in_vm(vm)
    finally:
        for rcs in dvs + vms:
            rcs.delete()


@pytest.mark.polarion("CNV-2183")
def test_private_registry_insecured_configmap(
    skip_upstream,
    namespace,
    images_private_registry_server,
    storage_class_matrix__function__,
):
    storage_class = [*storage_class_matrix__function__][0]
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
        storage_class=storage_class,
        volume_mode=storage_class_matrix__function__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv=dv) as vm_dv:
            utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.polarion("CNV-2182")
def test_private_registry_recover_after_missing_configmap(
    skip_upstream,
    namespace,
    images_private_registry_server,
    registry_config_map,
    storage_class_matrix__function__,
):
    storage_class = [*storage_class_matrix__function__][0]
    # creating DV before configmap with certificate is created
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-private-registry-with-no-configmap",
        namespace=namespace.name,
        url=f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
        cert_configmap=registry_config_map.name,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__function__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait_for_status(DataVolume.Status.IMPORT_SCHEDULED, timeout=300)
        dv.wait()
        with utils.create_vm_from_dv(dv) as vm_dv:
            utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.polarion("CNV-2344")
def test_private_registry_with_untrusted_certificate(
    skip_upstream,
    namespace,
    images_private_registry_server,
    registry_config_map,
    storage_class_matrix__function__,
):
    storage_class = [*storage_class_matrix__function__][0]
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-private-registry-with-untrusted-certificate",
        namespace=namespace.name,
        url=f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
        cert_configmap=registry_config_map.name,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__function__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv) as vm_dv:
            utils.check_disk_count_in_vm(vm_dv)

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
            storage_class=storage_class,
            volume_mode=storage_class_matrix__function__[storage_class]["volume_mode"],
        ) as dv:
            dv.wait_for_status(status=DataVolume.Status.IMPORT_IN_PROGRESS, timeout=300)
            wait_for_importer_container_message(
                importer_pod=dv.importer_pod, msg=ErrorMsg.EXIT_STATUS_1,
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
    storage_class = [*storage_class_matrix__function__][0]
    with utilities.storage.create_dv(
        source="registry",
        dv_name=dv_name,
        namespace=namespace.name,
        url=url,
        cert_configmap=cert_configmap,
        content_type=content_type,
        size=size,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__function__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv=dv) as vm_dv:
            utils.check_disk_count_in_vm(vm_dv)


# The following test is to show after imports fails because low capacity storage,
# we can overcome by updaing to the right requested volume size and import successfully
@pytest.mark.polarion("CNV-2024")
def test_public_registry_data_volume_dockerhub_low_capacity(
    namespace, storage_class_matrix__function__
):
    # negative flow - low capacity volume
    storage_class = [*storage_class_matrix__function__][0]
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-registry-dockerhub-low-capacity-dv",
        namespace=namespace.name,
        url=DOCKERHUB_IMAGE,
        content_type="",
        size="16Mi",
        storage_class=storage_class,
        volume_mode=storage_class_matrix__function__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=300,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        wait_for_importer_container_message(
            importer_pod=dv.importer_pod, msg=ErrorMsg.SHRINK_NOT_SUPPORTED,
        )

    # positive flow
    with utilities.storage.create_dv(
        source="registry",
        dv_name="import-registry-dockerhub-low-capacity-dv",
        namespace=namespace.name,
        url=DOCKERHUB_IMAGE,
        storage_class=storage_class,
        volume_mode=storage_class_matrix__function__[storage_class]["volume_mode"],
    ) as dv:
        dv.wait()
        with utils.create_vm_from_dv(dv=dv) as vm_dv:
            utils.check_disk_count_in_vm(vm_dv)


@pytest.mark.bugzilla(
    1725372, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.polarion("CNV-2150")
def test_public_registry_data_volume_dockerhub_archive(
    namespace, storage_class_matrix__function__
):
    storage_class = [*storage_class_matrix__function__][0]
    with pytest.raises(
        ApiException, match=r".*ContentType must be kubevirt when Source is Registry.*"
    ):
        with utilities.storage.create_dv(
            source="registry",
            dv_name="import-registry-archive",
            namespace=namespace.name,
            url=DOCKERHUB_IMAGE,
            content_type=DataVolume.ContentType.ARCHIVE,
            storage_class=storage_class,
            volume_mode=storage_class_matrix__function__[storage_class]["volume_mode"],
        ):
            return
