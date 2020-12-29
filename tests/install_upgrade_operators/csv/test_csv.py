from base64 import b64decode

import pytest
from resources.cluster_service_version import ClusterServiceVersion


# Check CSV properties like keywords, title, provided by, links etc.

EXPECTED_KEYWORDS_SET = {
    "KubeVirt",
    "Virtualization",
    "VM",
    "CNV",
    "Container-native virtualization",
    "Container native virtualization",
    "Virt",
    "Virtual",
}

EXPECTED_LINK_MAP = {
    "Source Code": "https://github.com/kubevirt",
    "OpenShift Virtualization": "https://www.openshift.com/learn/topics/virtualization/",
    "KubeVirt Project": "https://kubevirt.io",
}


@pytest.fixture()
def csv(admin_client):
    for csv in ClusterServiceVersion.get(
        dyn_client=admin_client, namespace="openshift-cnv"
    ):
        return csv


@pytest.mark.polarion("CNV-4456")
@pytest.mark.smoke
@pytest.mark.ocp_interop
def test_csv_keywords(csv):
    """
    Assert keywords. Check that each one of the expected keywords are actually there
    """
    assert EXPECTED_KEYWORDS_SET == set(csv.instance.spec.keywords)


@pytest.mark.polarion("CNV-4457")
@pytest.mark.smoke
@pytest.mark.ocp_interop
def test_csv_links(csv):
    """
    Check links list.
    """
    # links is a list of dicts, with keys of "name" and "url"
    # translate the links list to a single name:url dict
    csv_link_map = {
        link_dict.get("name"): link_dict.get("url")
        for link_dict in csv.instance.spec.links
    }
    # check that the links list contains all the required name:url pairs
    assert EXPECTED_LINK_MAP == csv_link_map
    # check that there are no duplication in links list
    assert len(EXPECTED_LINK_MAP) == len(csv.instance.spec.links)


@pytest.mark.polarion("CNV-4458")
@pytest.mark.smoke
@pytest.mark.ocp_interop
def test_csv_icon(csv):
    """
    Assert Icon/Logo.
    """
    assert len(csv.instance.spec.icon) == 1
    assert csv.instance.spec.icon[0].mediatype == "image/svg+xml"
    svg = b64decode(s=csv.instance.spec.icon[0].base64data)
    with open("tests/install_upgrade_operators/csv/logo.svg", "rb") as logo_file:
        expected_svg = logo_file.read()

    icon_match = svg == expected_svg
    assert icon_match


@pytest.mark.polarion("CNV-4376")
@pytest.mark.smoke
@pytest.mark.ocp_interop
def test_csv_properties(csv):
    """
    Asserting remaining csv properties.
    """
    assert csv.instance.spec.provider.name == "Red Hat"
    assert csv.instance.spec.displayName == "OpenShift Virtualization"

    annotations = csv.instance.metadata.annotations
    assert annotations.get("capabilities") == "Full Lifecycle"
    assert annotations.get("support") == "Red Hat"
