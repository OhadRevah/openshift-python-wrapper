import logging

from resources.datavolume import DataVolume
from resources.utils import TimeoutSampler
from utilities.virt import wait_for_vm_interfaces


LOGGER = logging.getLogger(__name__)


def wait_for_dvs_import_completed(dvs_list):
    def _dvs_import_completed():
        return all(map(lambda dv: dv.status == DataVolume.Status.SUCCEEDED, dvs_list))

    LOGGER.info("Wait for DVs import to end.")
    samples = TimeoutSampler(timeout=900, sleep=10, func=_dvs_import_completed,)
    for sample in samples:
        if sample:
            return


def wait_for_vms_interfaces(vms_list):
    for vm in vms_list:
        wait_for_vm_interfaces(vmi=vm.vmi, timeout=1100)
