import logging
import re

from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.ssp import SSP
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from openshift.dynamic.exceptions import NotFoundError
from pytest_testconfig import config as py_config

import utilities.storage
from utilities.constants import SSP_KUBEVIRT_HYPERCONVERGED, TIMEOUT_2MIN


LOGGER = logging.getLogger(__name__)


def wait_for_deleted_data_import_crons(data_import_crons):
    def _get_existing_data_import_crons(_data_import_crons, _auto_boot_sources):
        return [
            data_import_cron.name
            for data_import_cron in _data_import_crons
            if data_import_cron.exists
            and re.sub(
                utilities.storage.DATA_IMPORT_CRON_SUFFIX, "", data_import_cron.name
            )
            in _auto_boot_sources
        ]

    LOGGER.info("Wait for DataImportCrons deletion.")
    auto_boot_sources = matrix_auto_boot_sources()
    sample = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=5,
            func=_get_existing_data_import_crons,
            _data_import_crons=data_import_crons,
            _auto_boot_sources=auto_boot_sources,
        ):
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Some DataImportCrons are not deleted: {sample}")
        raise


def wait_for_at_least_one_auto_update_data_import_cron(admin_client, namespace):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=5,
            func=get_data_import_crons,
            admin_client=admin_client,
            namespace=namespace,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"No DataImportCrons found in {namespace.name}")
        raise


def matrix_auto_boot_sources():
    return [
        [*boot_source][0]
        for boot_source in py_config["auto_update_boot_sources_matrix"]
    ]


def get_data_import_crons(admin_client, namespace):
    return list(DataImportCron.get(dyn_client=admin_client, namespace=namespace.name))


def get_ssp_resource(admin_client, namespace):
    try:
        for ssp in SSP.get(
            dyn_client=admin_client,
            name=SSP_KUBEVIRT_HYPERCONVERGED,
            namespace=namespace.name,
        ):
            return ssp
    except NotFoundError:
        LOGGER.error(
            f"SSP CR {SSP_KUBEVIRT_HYPERCONVERGED} was not found in namespace {namespace.name}"
        )
        raise
