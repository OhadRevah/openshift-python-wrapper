import shlex
from subprocess import check_output

import pytest
from ocp_resources.custom_resource_definition import CustomResourceDefinition


@pytest.fixture()
def crds(admin_client):
    crds_to_check = []
    crds_to_check_suffix = ["kubevirt.io", "nmstate.io"]
    for crd in CustomResourceDefinition.get(dyn_client=admin_client):
        if any([crd.name.endswith(suffix) for suffix in crds_to_check_suffix]):
            crds_to_check.append(crd)
    return crds_to_check


@pytest.mark.polarion("CNV-8263")
def test_crds_cluster_readers_role(crds):
    cluster_readers = "system:cluster-readers"
    cannot_read = []
    for crd in crds:
        can_read = check_output(shlex.split(f"oc adm policy who-can get {crd.name}"))
        if cluster_readers not in str(can_read):
            cannot_read.append(crd.name)

    if cannot_read:
        cannot_read_str = "\n".join(cannot_read)
        pytest.fail(
            msg=f"The following crds are missing {cluster_readers} role:\n{cannot_read_str}"
        )