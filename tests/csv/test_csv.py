import pytest
from resources.cluster_service_version import ClusterServiceVersion


DEFAULT_KEYWORDS = [
    "KubeVirt",
    "Virtualization",
    "VM",
    "CNV",
    "Container-native virtualization",
    "Container native virtualization",
    "Virt",
    "Virtual",
]
NAMES = ["Source Code", "OpenShift virtualization", "KubeVirt Project"]
URLS = [
    "https://github.com/kubevirt",
    "https://www.openshift.com/learn/topics/virtualization/",
    "https://kubevirt.io",
]


@pytest.fixture()
def csv(default_client):
    for csv in ClusterServiceVersion.get(
        dyn_client=default_client, namespace="openshift-cnv"
    ):
        return csv


@pytest.mark.polarion("CNV-4376")
@pytest.mark.smoke
def test_csv_properties(csv):
    """
    Check CSV properties like keywords, title, provided by, links etc.
    """
    annotations = csv.instance.metadata.annotations

    # Checking List elements in another list.
    # Assert keywords.
    keywords = csv.instance.spec.keywords
    assert all(item in DEFAULT_KEYWORDS for item in keywords)

    # 'Links' contains list of dictionary, [key['name'] for key in links] this will create another
    # list which of key 'name'. Similarly for url which is value of dictionary.
    # Assert Links entities i.e. name and url.
    links = csv.instance.spec.links
    assert all(name in NAMES for name in [key["name"] for key in links])
    assert all(url in URLS for url in [value["url"] for value in links])

    # Assert Icon/Logo.
    assert csv.instance.spec.icon

    # Asserting remaining csv properties.
    assert csv.instance.spec.provider.name == "Red Hat"
    assert csv.instance.spec.displayName == "OpenShift virtualization"
    assert annotations.get("capabilities") == "Full Lifecycle"
    assert annotations.get("support") == "true"
