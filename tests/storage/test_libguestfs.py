import pexpect
import pytest
from ocp_resources.pod import Pod
from pytest_testconfig import config as py_config

from utilities.constants import Images


pytestmark = pytest.mark.post_upgrade


@pytest.fixture()
def virtctl_libguestfs(data_volume_scope_function):
    guestfs_proc = pexpect.spawn(
        f"virtctl guestfs {data_volume_scope_function.name} -n {data_volume_scope_function.namespace}"
    )
    guestfs_proc.send("\n\n")
    guestfs_proc.expect("#", timeout=60)
    yield guestfs_proc
    guestfs_proc.sendcontrol(char="d")
    guestfs_proc.expect(pexpect.EOF, timeout=60)
    guestfs_proc.close()
    Pod(
        name=f"libguestfs-tools-{data_volume_scope_function.name}",
        namespace=data_volume_scope_function.namespace,
    ).wait_deleted()


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_scope_function",
    [
        pytest.param(
            {
                "dv_name": "guestfs-dv-cnv-6566",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
                "storage_class": py_config["default_storage_class"],
            },
            marks=(pytest.mark.polarion("CNV-6566")),
        ),
    ],
    indirect=True,
)
def test_virtctl_libguestfs(data_volume_scope_function, virtctl_libguestfs):
    virtctl_libguestfs.sendline("libguestfs-test-tool")
    virtctl_libguestfs.expect("===== TEST FINISHED OK =====", timeout=60)
