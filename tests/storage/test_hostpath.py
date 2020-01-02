# -*- coding: utf-8 -*-

"""
Hostpath Provisioner test suite
"""

import logging

import pytest
import tests.storage.utils as storage_utils
from pytest_testconfig import config as py_config
from resources.datavolume import DataVolume
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.pod import Pod
from resources.storage_class import StorageClass
from utilities.infra import Images, get_images_external_http_server
from utilities.storage import create_dv


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def skip_when_hpp_no_immediate(skip_test_if_no_hpp_sc, hpp_storage_class):
    LOGGER.debug("Use 'skip_when_hpp_no_immediate' fixture...")
    if (
        not hpp_storage_class.instance["volumeBindingMode"]
        == StorageClass.VolumeBindingMode.Immediate
    ):
        pytest.skip(msg="Test only run when volumeBindingMode is Immediate")


@pytest.fixture(scope="module")
def skip_when_hpp_no_waitforfirstconsumer(skip_test_if_no_hpp_sc, hpp_storage_class):
    LOGGER.debug("Use 'skip_when_hpp_no_waitforfirstconsumer' fixture...")
    if (
        not hpp_storage_class.instance["volumeBindingMode"]
        == StorageClass.VolumeBindingMode.WaitForFirstConsumer
    ):
        pytest.skip(msg="Test only run when volumeBindingMode is WaitForFirstConsumer")


def verify_image_location_via_dv_pod_with_pvc(dv, nodes):
    dv.wait()
    with storage_utils.PodWithPVC(
        namespace=dv.namespace,
        name=f"{dv.name}-pod",
        pvc_name=dv.pvc.name,
        volume_mode=py_config["default_volume_mode"],
    ) as pod:
        pod.wait_for_status(status="Running")
        LOGGER.debug("Check pod location...")
        assert pod.instance["spec"]["nodeName"] == nodes[0].name
        LOGGER.debug("Check image location...")
        assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


def verify_image_location_via_dv_virt_launcher_pod(dv, nodes):
    dv.wait()
    with storage_utils.create_vm_from_dv(dv) as vm:
        vm.vmi.wait_until_running()
        v_pod = vm.vmi.virt_launcher_pod
        LOGGER.debug("Check pod location...")
        assert v_pod.instance["spec"]["nodeName"] == nodes[0].name
        LOGGER.debug("Check image location...")
        assert "disk.img" in v_pod.execute(
            command=["ls", "-1", "/var/run/kubevirt-private/vmi-disks/dv-disk"]
        )


@pytest.mark.polarion("CNV-2817")
def test_hostpath_pod_reference_pvc(storage_ns, nodes, skip_test_if_no_hpp_sc):
    """
    Check that after disk image is written to the PVC which has been provisioned on the specified node,
    Pod can use this image.
    """
    with create_dv(
        source="http",
        dv_name="cnv-2817",
        namespace=storage_ns.name,
        url=f"{get_images_external_http_server()}{Images.Fedora.DIR}/{Images.Fedora.FEDORA29_IMG}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="20Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=py_config["default_volume_mode"],
        hostpath_node=nodes[0].name,
    ) as dv:
        verify_image_location_via_dv_pod_with_pvc(dv, nodes)


@pytest.mark.polarion("CNV-3354")
def test_hpp_not_specify_node_immediate(
    storage_ns, skip_test_if_no_hpp_sc, skip_when_hpp_no_immediate
):
    """
    Negative case
    Check that PVC should remain Pending when hostpath node was not specified
    and the volumeBindingMode of hostpath-provisioner StorageClass is 'Immediate'
    """
    with create_dv(
        source="http",
        dv_name="cnv-3354",
        namespace=storage_ns.name,
        url=f"{get_images_external_http_server()}{Images.Windows.WIN16_IMG}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="35Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=py_config["default_volume_mode"],
    ) as dv:
        dv.wait_for_status(
            status=dv.Status.PENDING, timeout=120, stop_status=dv.Status.SUCCEEDED
        )


@pytest.mark.polarion("CNV-3228")
def test_hpp_specify_node_immediate(
    storage_ns, nodes, skip_test_if_no_hpp_sc, skip_when_hpp_no_immediate
):
    """
    Check that the PVC will bound PV and DataVolume status becomes Succeeded once importer Pod finished importing
    when PVC is annotated to a specified node and the volumeBindingMode of hostpath-provisioner StorageClass is
    'Immediate'
    """
    with create_dv(
        source="http",
        dv_name="cnv-3228",
        namespace=storage_ns.name,
        url=f"{get_images_external_http_server()}{Images.Rhel.RHEL8_0_IMG}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="35Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=py_config["default_volume_mode"],
        hostpath_node=nodes[0].name,
    ) as dv:
        dv.wait(timeout=600)


@pytest.mark.parametrize(
    ("image_name", "dv_name"),
    [
        pytest.param(
            Images.Cirros.QCOW2_IMG,
            "cnv-2767-qcow2",
            marks=(pytest.mark.polarion("CNV-2767")),
        ),
        pytest.param(
            Images.Cirros.RAW_IMG,
            "cnv-2767-raw",
            marks=(pytest.mark.polarion("CNV-2767")),
        ),
    ],
)
def test_hostpath_http_import_dv(
    storage_ns,
    dv_name,
    image_name,
    nodes,
    skip_test_if_no_hpp_sc,
    skip_when_hpp_no_immediate,
):
    """
    Check that CDI importing from HTTP endpoint works well with hostpath-provisioner
    """
    with create_dv(
        source="http",
        dv_name=dv_name,
        namespace=storage_ns.name,
        content_type=DataVolume.ContentType.KUBEVIRT,
        url=f"{get_images_external_http_server()}{Images.Cirros.DIR}/{image_name}",
        size="500Mi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=py_config["default_volume_mode"],
        hostpath_node=nodes[0].name,
    ) as dv:
        verify_image_location_via_dv_virt_launcher_pod(dv, nodes)


@pytest.mark.polarion("CNV-3227")
def test_hpp_pvc_without_specify_node_waitforfirstconsumer(
    storage_ns, skip_test_if_no_hpp_sc, skip_when_hpp_no_waitforfirstconsumer
):
    """
    Check that in the condition of the volumeBindingMode of hostpath-provisioner StorageClass is 'WaitForFirstConsumer',
    if you do not specify the node on the PVC, it will remain Pending.
    The PV will be created only and PVC get bound when the first Pod using this PVC is scheduled.
    """
    with PersistentVolumeClaim(
        name="cnv-3227",
        namespace=storage_ns.name,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
    ) as pvc:
        pvc.wait_for_status(
            pvc.Status.PENDING, timeout=60, stop_status=pvc.Status.BOUND
        )
        with storage_utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=DataVolume.VolumeMode.FILE,
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING, timeout=180)
            pvc.wait_for_status(status=pvc.Status.BOUND, timeout=60)
            assert (
                pod.instance.spec.nodeName
                == pvc.instance.metadata.annotations[
                    "volume.kubernetes.io/selected-node"
                ]
            )


@pytest.mark.polarion("CNV-2771")
def test_hpp_upload_virtctl(
    storage_ns, tmpdir, skip_test_if_no_hpp_sc, skip_when_hpp_no_waitforfirstconsumer
):
    """
    Check that upload disk image via virtcl tool works
    """
    local_name = f"{tmpdir}/{Images.Fedora.FEDORA29_IMG}"
    remote_name = f"{Images.Fedora.DIR}/{Images.Fedora.FEDORA29_IMG}"
    storage_utils.downloaded_image(remote_name=remote_name, local_name=local_name)
    pvc_name = "cnv-2771"
    virtctl_upload = storage_utils.virtctl_upload(
        namespace=storage_ns.name,
        image_path=local_name,
        pvc_size="25Gi",
        pvc_name=pvc_name,
        storage_class=StorageClass.Types.HOSTPATH,
    )
    LOGGER.debug(virtctl_upload)
    assert virtctl_upload
    pvc = PersistentVolumeClaim(namespace=storage_ns.name, name=pvc_name)
    assert pvc.bound()
    scratch_pvc = PersistentVolumeClaim(
        namespace=storage_ns.name, name=f"{pvc_name}-scratch"
    )
    pod = Pod(namespace=storage_ns.name, name=f"cdi-upload-{pvc.name}")
    assert (
        pvc.instance.metadata.annotations.get("volume.kubernetes.io/selected-node")
        == pod.instance.spec.nodeName
        and scratch_pvc.instance.metadata.annotations.get(
            "volume.kubernetes.io/selected-node"
        )
        == pod.instance.spec.nodeName
    ), "No 'volume.kubernetes.io/selected-node' annotation found on PVC"
