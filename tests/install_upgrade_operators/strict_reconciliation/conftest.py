import logging

import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import ConflictError

from tests.conftest import get_hyperconverged_resource


LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def deleted_stanza_on_hco_cr(
    request, hyperconverged_resource_scope_function, admin_client, hco_namespace
):
    # using retry logic to avoid failing due to ConflictError
    # raised by the validating webhook due to lately propagated side effects
    # of the previous change
    backups = []
    samples = TimeoutSampler(
        wait_timeout=20,
        sleep=2,
        exceptions=ConflictError,
        func=replace_hco_cr,
        rpatch=request.param,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    try:
        for sample in samples:
            if sample:
                backups = sample
                break
    except TimeoutExpiredError:
        LOGGER.error("Timeout trying to altering the hyperconverged CR.")
        raise
    yield
    for backup in backups:
        # sending only the original spec stanza to avoid a sure conflict due to
        # resourceVersion that got updated by the previous call.
        # ResourceEditor is currently bugged on this and so it's going to fail for sure
        # in the teardown phase with ConflictError: 409
        samples = TimeoutSampler(
            wait_timeout=20,
            sleep=2,
            exceptions=ConflictError,
            func=replace_hco_cr,
            rpatch=backup.instance.to_dict()["spec"],
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        try:
            for sample in samples:
                if sample:
                    break
        except TimeoutExpiredError:
            LOGGER.error("Timeout restoring the initial hyperconverged CR.")
            raise


def replace_hco_cr(rpatch, admin_client, hco_namespace):
    # fetch hyperconverged_resource each time instead of using a single
    # fixture to be sure to get it with an up to date resourceVersion
    # as needed for action=replace
    hyperconverged_resource = get_hyperconverged_resource(
        client=admin_client, hco_ns_name=hco_namespace.name
    )

    # we have to use action="replace" to send a put to delete existing fields
    # (update, the default, will only update existing fields).
    reseditor = ResourceEditor(
        patches={hyperconverged_resource: rpatch}, action="replace"
    )
    reseditor.update(backup_resources=True)
    return reseditor.backups
