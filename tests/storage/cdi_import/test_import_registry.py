# -*- coding: utf-8 -*-

import pytest
import os

from pytest_testconfig import config as py_config
from resources.datavolume import ImportFromRegistryDataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.configmap import ConfigMap
from tests.storage import utils


DOCKERHUB_IMAGE = "docker://kubevirt/cirros-registry-disk-demo"
QUAY_IMAGE = "docker://quay.io/kubevirt/cirros-registry-disk-demo"
PRIVATE_REGISTRY_HOST = "docker://cnv-qe-server.rhevdev.lab.eng.rdu2.redhat.com"
PRIVATE_REGISTRY_IMAGE = "cirros-registry-disk-demo:latest"
PRIVATE_REGISTRY_URL = f"{PRIVATE_REGISTRY_HOST}:8443/{PRIVATE_REGISTRY_IMAGE}"
PRIVATE_INSECURED_REGISTRY_URL = (
    f"{PRIVATE_REGISTRY_HOST}:5000/{PRIVATE_REGISTRY_IMAGE}"
)


@pytest.mark.polarion("CNV-2183")
def test_private_registry_insecured_configmap(storage_ns):
    c = ConfigMap(
        namespace="kubevirt-hyperconverged", name="cdi-insecure-registries", data=None
    )

    c.update(
        resource_dict={
            "data": {"mykey": "cnv-qe-server.rhevdev.lab.eng.rdu2.redhat.com:5000"},
            "metadata": {"name": "cdi-insecure-registries"},
        }
    )
    create_dv_and_vm(
        "import-private-insecured-registry",
        storage_ns.name,
        PRIVATE_INSECURED_REGISTRY_URL,
        None,
        ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
        "5Gi",
    )


@pytest.mark.polarion("CNV-2182")
def test_private_registry_recover_after_missing_configmap(storage_ns):
    # creating DV before configmap with certificate is created
    with ImportFromRegistryDataVolume(
        name="import-private-registry-with-no-configmap",
        namespace=storage_ns.name,
        url=PRIVATE_REGISTRY_URL,
        content_type=ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
        size="5Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        cert_configmap="registry-cert-configmap",
    ) as dv:
        assert dv.wait_for_status("ImportScheduled", timeout=300)
        # create the configmap with the untrusted certificate
        with ConfigMap(
            name="registry-cert-configmap", namespace=storage_ns.name, data=get_cert()
        ) as configmap:
            assert configmap is not None
            assert dv.wait_for_status(status="Succeeded", timeout=300)
            assert PersistentVolumeClaim(name=dv.name, namespace=dv.namespace).bound()
            utils.create_vm_with_dv(dv)


@pytest.mark.polarion("CNV-2344")
def test_private_registry_with_untrusted_certificate(storage_ns):
    with ConfigMap(
        name="registry-cert-configmap", namespace=storage_ns.name, data=get_cert()
    ) as configmap:
        assert configmap is not None
        create_dv_and_vm(
            "import-private-registry-with-untrusted-certificate",
            storage_ns.name,
            PRIVATE_REGISTRY_URL,
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
            url=PRIVATE_REGISTRY_URL,
            content_type="",
            size="5Gi",
            storage_class=py_config["storage_defaults"]["storage_class"],
            cert_configmap=configmap.name,
        ) as dv:
            assert dv.wait_for_status(status="Failed", timeout=300)


def get_cert():
    path = os.path.join("tests/storage/cdi_import", "tlsregistry.crt")
    with open(path, "r") as cert_content:
        data = cert_content.read()
    return data


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
        assert dv.wait_for_status(status="Succeeded", timeout=300)
        assert PersistentVolumeClaim(name=dv.name, namespace=dv.namespace).bound()
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
            marks=(pytest.mark.polarion("CNV-2149")),
        ),
        pytest.param(
            "import-registry-dockerhub-no-content-type-dv",
            DOCKERHUB_IMAGE,
            None,
            None,
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2197")),
        ),
        pytest.param(
            "import-registry-dockerhub-empty-content-type-dv",
            DOCKERHUB_IMAGE,
            None,
            "",
            "5Gi",
            marks=(pytest.mark.polarion("CNV-2195")),
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
        size="10Mi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        cert_configmap=None,
    ) as dv:
        assert dv.wait_for_status(status="Failed", timeout=300)

    # positive flow
    create_dv_and_vm(
        "import-registry-dockerhub-low-capacity-dv",
        storage_ns.name,
        DOCKERHUB_IMAGE,
        None,
        ImportFromRegistryDataVolume.ContentType.KUBEVIRT,
        "5Gi",
    )


@pytest.mark.bugzilla(1725372, skip_when=lambda bug: bug.status != "VERIFIED")
@pytest.mark.polarion("CNV-2150")
def test_public_registry_data_volume_dockerhub_archive(storage_ns):
    with ImportFromRegistryDataVolume(
        name="import-registry-archive",
        namespace=storage_ns.name,
        url=DOCKERHUB_IMAGE,
        content_type=ImportFromRegistryDataVolume.ContentType.ARCHIVE,
        size="5Gi",
        storage_class=py_config["storage_defaults"]["storage_class"],
        cert_configmap=None,
    ) as dv:
        assert dv is None
