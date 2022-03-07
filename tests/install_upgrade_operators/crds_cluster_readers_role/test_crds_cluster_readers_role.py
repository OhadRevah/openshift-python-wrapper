import shlex
from subprocess import check_output

import pytest
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.resource import Resource

from utilities.infra import LOGGER, is_bug_open


KUBEVIRT_IO = Resource.ApiGroup.KUBEVIRT_IO
NMSTATE_IO = Resource.ApiGroup.NMSTATE_IO


@pytest.fixture()
def crds(admin_client):
    crds_to_check = []
    crds_to_check_suffix = [KUBEVIRT_IO, NMSTATE_IO]
    for crd in CustomResourceDefinition.get(dyn_client=admin_client):
        if any([crd.name.endswith(suffix) for suffix in crds_to_check_suffix]):
            crds_to_check.append(crd)
    return crds_to_check


# TODO: Remove bug once it is fixed.
@pytest.fixture()
def crds_if_bugzilla_not_closed():
    bugzilla_crds_name_dict = {
        "2057142": [
            f"cdiconfigs.cdi.{KUBEVIRT_IO}",
            f"dataimportcrons.cdi.{KUBEVIRT_IO}",
            f"storageprofiles.cdi.{KUBEVIRT_IO}",
            f"datasources.cdi.{KUBEVIRT_IO}",
            f"objecttransfers.cdi.{KUBEVIRT_IO}",
        ],
        "2022745": [
            f"nodenetworkconfigurationenactments.{NMSTATE_IO}",
            f"nodenetworkconfigurationpolicies.{NMSTATE_IO}",
            f"nodenetworkstates.{NMSTATE_IO}",
        ],
    }
    skipped_crds = []
    for bug_id, crds_name in bugzilla_crds_name_dict.items():
        if is_bug_open(bug_id=bug_id):
            skipped_crds.extend(crds_name)
            LOGGER.info(f"CRD {crds_name} skipped due to bugzilla '{bug_id}'")
    return skipped_crds


@pytest.mark.polarion("CNV-8263")
def test_crds_cluster_readers_role(crds, crds_if_bugzilla_not_closed):
    cluster_readers = "system:cluster-readers"
    cannot_read = []
    for crd in crds:
        can_read = check_output(shlex.split(f"oc adm policy who-can get {crd.name}"))
        if (
            cluster_readers not in str(can_read)
            and crd.name not in crds_if_bugzilla_not_closed
        ):
            cannot_read.append(crd.name)

    if cannot_read:
        cannot_read_str = "\n".join(cannot_read)
        pytest.fail(
            msg=f"The following crds are missing {cluster_readers} role:\n{cannot_read_str}"
        )
