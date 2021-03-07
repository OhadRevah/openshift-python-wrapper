import pytest_testconfig
from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_class import StorageClass


global config
global_config = pytest_testconfig.load_python(
    py_file="tests/global_config.py", encoding="utf-8"
)

no_unprivileged_client = True
mtv_namespace = "openshift-rhmtv"

storage_class_matrix = [
    {
        StorageClass.Types.NFS: {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWX,
        }
    },
    {
        StorageClass.Types.CEPH_RBD: {
            "volume_mode": DataVolume.VolumeMode.BLOCK,
            "access_mode": DataVolume.AccessMode.RWX,
            "default": True,
        }
    },
]


for _dir in dir():
    val = locals()[_dir]
    if not (
        isinstance(val, bool)
        or isinstance(val, list)
        or isinstance(val, dict)
        or isinstance(val, str)
    ):
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
