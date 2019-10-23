# -*- coding: utf-8 -*-
import multiprocessing

import pytest
from kubernetes.client.rest import ApiException
from pytest_testconfig import config as py_config
from resources.configmap import ConfigMap
from resources.datavolume import ImportFromRegistryDataVolume
from tests.storage import utils
from utilities import console
from utilities.infra import BUG_STATUS_CLOSED, get_cert
from utilities.virt import VirtualMachineForTests


DOCKERHUB_IMAGE = "docker://kubevirt/cirros-registry-disk-demo"
QUAY_IMAGE = "docker://quay.io/kubevirt/cirros-registry-disk-demo"
PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE = "cirros-registry-disk-demo:latest"
PRIVATE_REGISTRY_CIRROS_RAW_IMAGE = "cirros.raw:latest"
PRIVATE_REGISTRY_CIRROS_QCOW2_IMAGE = "cirros-qcow2.img:latest"


@pytest.mark.skipif(
    py_config["distribution"] == "upstream",
    reason="importing from private registry for d/s",
)
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
def test_private_registry_cirros(storage_ns, images_private_registry_server, file_name):
    with ConfigMap(
        name="registry-cert-configmap",
        namespace=storage_ns.name,
        data=get_cert("registry_cert"),
    ) as configmap:
        create_dv_and_vm(
            "import-private-registry-cirros-image",
            storage_ns.name,
            f"{images_private_registry_server}:8443/{file_name}",
            configmap.name,
            ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
            "5Gi",
        )


@pytest.mark.polarion("CNV-2198")
def test_disk_image_not_conform_to_registy_disk(storage_ns):
    with ImportFromRegistryDataVolume(
        name="image-registry-not-conform-registrydisk",
        namespace=storage_ns.name,
        url="docker://docker.io/cirros",
        content_type=ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
        size="5Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        cert_configmap=None,
    ) as dv:
        dv.wait_for_status(
            status=ImportFromRegistryDataVolume.Status.FAILED, timeout=300
        )


@pytest.mark.polarion("CNV-2042")
def test_public_registry_multiple_data_volume(storage_ns):
    dvs = []
    vms = []
    dvs_processes = []
    vms_processes = []
    try:
        for dv in ("dv1", "dv2", "dv3"):
            rdv = ImportFromRegistryDataVolume(
                name=f"import-registry-dockerhub-{dv}",
                namespace=storage_ns.name,
                url=DOCKERHUB_IMAGE,
                content_type=ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
                size="5Gi",
                storage_class=py_config["storage_defaults"]["storage_class"],
            )

            dv_process = multiprocessing.Process(target=rdv.create)
            dv_process.start()
            dvs_processes.append(dv_process)
            dvs.append(rdv)

        for dvp in dvs_processes:
            dvp.join()

        for dv in dvs:
            dv.wait_for_status(status=rdv.Status.SUCCEEDED, timeout=300)

        for vm in [vm.name for vm in dvs]:
            rvm = VirtualMachineForTests(name=vm, namespace=storage_ns.name, dv=vm)
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
            with console.Cirros(vm=vm) as vm_console:
                vm_console.sendline("lsblk | grep disk | wc -l")
                vm_console.expect("2", timeout=60)
    finally:
        for rcs in dvs + vms:
            rcs.delete()


@pytest.mark.skipif(
    py_config["distribution"] == "upstream",
    reason="importing from private registry for d/s",
)
@pytest.mark.polarion("CNV-2183")
def test_private_registry_insecured_configmap(
    storage_ns, images_private_registry_server
):

    server = images_private_registry_server[9:]
    c = ConfigMap(
        namespace=py_config["hco_namespace"], name="cdi-insecure-registries", data=None
    )

    c.update(
        resource_dict={
            "data": {"mykey": f"{server}:5000"},
            "metadata": {"name": "cdi-insecure-registries"},
        }
    )
    create_dv_and_vm(
        "import-private-insecured-registry",
        storage_ns.name,
        f"{images_private_registry_server}:5000/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
        None,
        ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
        "5Gi",
    )


@pytest.mark.skipif(
    py_config["distribution"] == "upstream",
    reason="importing from private registry for d/s",
)
@pytest.mark.polarion("CNV-2182")
def test_private_registry_recover_after_missing_configmap(
    storage_ns, images_private_registry_server
):
    # creating DV before configmap with certificate is created
    with ImportFromRegistryDataVolume(
        name="import-private-registry-with-no-configmap",
        namespace=storage_ns.name,
        url=f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
        content_type=ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
        size="5Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        cert_configmap="registry-cert-configmap",
    ) as dv:
        dv.wait_for_status(
            ImportFromRegistryDataVolume.Status.IMPORT_SCHEDULED, timeout=300
        )
        # create the configmap with the untrusted certificate
        with ConfigMap(
            name="registry-cert-configmap",
            namespace=storage_ns.name,
            data=get_cert("registry_cert"),
        ) as configmap:
            assert configmap is not None
            dv.wait()
            utils.create_vm_with_dv(dv)


@pytest.mark.skipif(
    py_config["distribution"] == "upstream",
    reason="importing from private registry for d/s",
)
@pytest.mark.polarion("CNV-2344")
def test_private_registry_with_untrusted_certificate(
    storage_ns, images_private_registry_server
):
    with ConfigMap(
        name="registry-cert-configmap",
        namespace=storage_ns.name,
        data=get_cert("registry_cert"),
    ) as configmap:
        assert configmap is not None
        create_dv_and_vm(
            "import-private-registry-with-untrusted-certificate",
            storage_ns.name,
            f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
            configmap.name,
            ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
            "5Gi",
        )
        # negative flow - remove certificate from configmap
        configmap.update(
            resource_dict={
                "data": {"tlsregistry.crt": ""},
                "metadata": {"name": "registry-cert-configmap"},
            }
        )
        with ImportFromRegistryDataVolume(
            name="import-private-registry-no-certificate",
            namespace=storage_ns.name,
            url=f"{images_private_registry_server}:8443/{PRIVATE_REGISTRY_CIRROS_DEMO_IMAGE}",
            content_type="",
            size="5Gi",
            storage_class=py_config["storage_defaults"]["storage_class"],
            cert_configmap=configmap.name,
        ) as dv:
            dv.wait_for_status(
                status=ImportFromRegistryDataVolume.Status.FAILED, timeout=300
            )


def create_dv_and_vm(dv_name, namespace, url, cert_configmap, content_type, size):
    with ImportFromRegistryDataVolume(
        name=dv_name,
        namespace=namespace,
        url=url,
        content_type=content_type,
        size=size,
        storage_class=py_config["storage_defaults"]["storage_class"],
        cert_configmap=cert_configmap,
    ) as dv:
        dv.wait()
        utils.create_vm_with_dv(dv)


@pytest.mark.parametrize(
    ("dv_name", "url", "cert_configmap", "content_type", "size"),
    [
        pytest.param(
            "import-registry-dockerhub-dv",
            DOCKERHUB_IMAGE,
            None,
            ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
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
            ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
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
    storage_ns, dv_name, url, cert_configmap, content_type, size
):
    create_dv_and_vm(dv_name, storage_ns.name, url, cert_configmap, content_type, size)


# The following test is to show after imports fails because low capacity storage,
# we can overcome by updaing to the right requested volume size and import successfully
@pytest.mark.polarion("CNV-2024")
def test_public_registry_data_volume_dockerhub_low_capacity(storage_ns):
    # negative flow - low capacity volume
    with ImportFromRegistryDataVolume(
        name="import-registry-dockerhub-low-capacity-dv",
        namespace=storage_ns.name,
        url=DOCKERHUB_IMAGE,
        content_type="",
        size="16Mi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        cert_configmap=None,
    ) as dv:
        dv.wait_for_status(
            status=ImportFromRegistryDataVolume.Status.FAILED, timeout=300
        )

    # positive flow
    create_dv_and_vm(
        "import-registry-dockerhub-low-capacity-dv",
        storage_ns.name,
        DOCKERHUB_IMAGE,
        None,
        ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
        "5Gi",
    )


@pytest.mark.bugzilla(
    1725372, skip_when=lambda bug: bug.status not in BUG_STATUS_CLOSED
)
@pytest.mark.polarion("CNV-2150")
def test_public_registry_data_volume_dockerhub_archive(storage_ns):
    with pytest.raises(
        ApiException, match=r".*ContentType must be kubevirt when Source is Registry.*"
    ):
        with ImportFromRegistryDataVolume(
            name="import-registry-archive",
            namespace=storage_ns.name,
            url=DOCKERHUB_IMAGE,
            content_type=ImportFromRegistryDataVolume.ContentType.ARCHIVE,
            size="5Gi",
            storage_class=py_config["storage_defaults"]["storage_class"],
            cert_configmap=None,
        ):
            return
