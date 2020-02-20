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


def verify_image_location_via_dv_pod_with_pvc(dv, schedulable_nodes):
    dv.wait()
    with storage_utils.PodWithPVC(
        namespace=dv.namespace,
        name=f"{dv.name}-pod",
        pvc_name=dv.pvc.name,
        volume_mode=py_config["default_volume_mode"],
    ) as pod:
        pod.wait_for_status(status="Running")
        LOGGER.debug("Check pod location...")
        assert pod.instance["spec"]["nodeName"] == schedulable_nodes[0].name
        LOGGER.debug("Check image location...")
        assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


def verify_image_location_via_dv_virt_launcher_pod(dv, schedulable_nodes):
    dv.wait()
    with storage_utils.create_vm_from_dv(dv) as vm:
        vm.vmi.wait_until_running()
        v_pod = vm.vmi.virt_launcher_pod
        LOGGER.debug("Check pod location...")
        assert v_pod.instance["spec"]["nodeName"] == schedulable_nodes[0].name
        LOGGER.debug("Check image location...")
        assert "disk.img" in v_pod.execute(
            command=["ls", "-1", "/var/run/kubevirt-private/vmi-disks/dv-disk"]
        )


def assert_provision_on_node_annotation(pvc, node_name, type_):
    provision_on_node = "kubevirt.io/provisionOnNode"
    assert pvc.instance.metadata.annotations.get(provision_on_node) == node_name
    f"No '{provision_on_node}' annotation found on {type_} PVC"


def assert_selected_node_annotation(pvc, pod, type_):
    selected_node = "volume.kubernetes.io/selected-node"
    assert (
        pvc.instance.metadata.annotations.get(selected_node)
        == pod.instance.spec.nodeName
    ), f"No '{selected_node}' annotation found on {type_} PVC"


def get_pod_by_name_prefix(default_client, pod_prefix, namespace):
    pods = [
        pod
        for pod in Pod.get(dyn_client=default_client, namespace=namespace)
        if pod.name.startswith(pod_prefix)
    ]
    return pods[0]


@pytest.mark.polarion("CNV-2817")
def test_hostpath_pod_reference_pvc(
    skip_test_if_no_hpp_sc, storage_ns, schedulable_nodes
):
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
        volume_mode=DataVolume.VolumeMode.FILE,
        hostpath_node=schedulable_nodes[0].name,
    ) as dv:
        verify_image_location_via_dv_pod_with_pvc(
            dv=dv, schedulable_nodes=schedulable_nodes
        )


@pytest.mark.polarion("CNV-3354")
def test_hpp_not_specify_node_immediate(skip_when_hpp_no_immediate, storage_ns):
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
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.wait_for_status(
            status=dv.Status.PENDING, timeout=120, stop_status=dv.Status.SUCCEEDED
        )


@pytest.mark.polarion("CNV-3228")
def test_hpp_specify_node_immediate(
    skip_when_hpp_no_immediate, storage_ns, schedulable_nodes
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
        volume_mode=DataVolume.VolumeMode.FILE,
        hostpath_node=schedulable_nodes[0].name,
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
    skip_when_hpp_no_immediate, storage_ns, dv_name, image_name, schedulable_nodes,
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
        volume_mode=DataVolume.VolumeMode.FILE,
        hostpath_node=schedulable_nodes[0].name,
    ) as dv:
        verify_image_location_via_dv_virt_launcher_pod(
            dv=dv, schedulable_nodes=schedulable_nodes
        )


@pytest.mark.polarion("CNV-3227")
def test_hpp_pvc_without_specify_node_waitforfirstconsumer(
    skip_when_hpp_no_waitforfirstconsumer, storage_ns,
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


@pytest.mark.polarion("CNV-3280")
def test_hpp_pvc_specify_node_waitforfirstconsumer(
    skip_when_hpp_no_waitforfirstconsumer, storage_ns, schedulable_nodes,
):
    """
    Check that kubevirt.io/provisionOnNode annotation works in WaitForFirstConsumer mode.
    Even in this mode, the annotation still causes an immediate bind on the specified node.
    """
    with PersistentVolumeClaim(
        name="cnv-3280",
        namespace=storage_ns.name,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        hostpath_node=schedulable_nodes[0].name,
    ) as pvc:
        pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=60)
        assert_provision_on_node_annotation(
            pvc=pvc, node_name=schedulable_nodes[0].name, type_="regular"
        )
        with storage_utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=DataVolume.VolumeMode.FILE,
        ) as pod:
            pod.wait_for_status(status=Pod.Status.RUNNING, timeout=180)
            assert pod.instance.spec.nodeName == schedulable_nodes[0].name


@pytest.mark.polarion("CNV-2771")
def test_hpp_upload_virtctl(skip_when_hpp_no_waitforfirstconsumer, storage_ns, tmpdir):
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


@pytest.mark.polarion("CNV-2769")
def test_hostpath_upload_dv_with_token(
    skip_test_if_no_hpp_sc, storage_ns, tmpdir, schedulable_nodes,
):
    dv_name = "cnv-2769"
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    remote_name = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
    storage_utils.downloaded_image(
        remote_name=remote_name, local_name=local_name,
    )
    with create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=storage_ns.name,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        hostpath_node=schedulable_nodes[0].name,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=180)
        storage_utils.upload_token_request(
            storage_ns_name=dv.namespace, pvc_name=dv.pvc.name, data=local_name
        )
        dv.wait()
        verify_image_location_via_dv_pod_with_pvc(
            dv=dv, schedulable_nodes=schedulable_nodes
        )


@pytest.mark.parametrize(
    ("dv_name", "url"),
    [
        pytest.param(
            "cnv-3326-docker",
            f"docker://docker.io/kubevirt/{Images.Cirros.DISK_DEMO}",
            marks=(pytest.mark.polarion("CNV-3326")),
        ),
        pytest.param(
            "cnv-3326-quay",
            f"docker://quay.io/kubevirt/{Images.Cirros.DISK_DEMO}",
            marks=(pytest.mark.polarion("CNV-3326")),
        ),
    ],
)
def test_hostpath_registry_import_dv(
    skip_when_hpp_no_waitforfirstconsumer,
    hpp_storage_class,
    storage_ns,
    dv_name,
    url,
    schedulable_nodes,
):
    """
    Check that when importing image from public registry with kubevirt.io/provisionOnNode annotation works well.
    On WaitForFirstConsumer Mode, the 'volume.kubernetes.io/selected-node' annotation will be added to scratch PVC.
    """
    with create_dv(
        source="registry",
        dv_name=dv_name,
        namespace=storage_ns.name,
        url=url,
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        hostpath_node=schedulable_nodes[0].name,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.scratch_pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=300
        )
        dv.importer_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=300)
        assert_selected_node_annotation(
            pvc=dv.scratch_pvc, pod=dv.importer_pod, type_="scratch"
        )
        assert_provision_on_node_annotation(
            pvc=dv.pvc, node_name=schedulable_nodes[0].name, type_="import"
        )
        dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=300)
        verify_image_location_via_dv_virt_launcher_pod(
            dv=dv, schedulable_nodes=schedulable_nodes
        )


@pytest.mark.polarion("CNV-3516")
def test_hostpath_clone_dv_wffc(
    skip_when_hpp_no_waitforfirstconsumer, default_client, storage_ns,
):
    """
    Check that in case of WaitForFirstConsumer binding mode, without annotating the source/target DV to a node,
    CDI clone function works well. The PVCs will have an annotation 'volume.kubernetes.io/selected-node' containing
    the node name where the pod is scheduled on.
    """
    with create_dv(
        source="http",
        dv_name="cnv-3516-source-dv",
        namespace=storage_ns.name,
        content_type=DataVolume.ContentType.KUBEVIRT,
        url=f"{get_images_external_http_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        size="6Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as source_dv:
        source_dv.pvc.wait(timeout=300)
        importer_pod = get_pod_by_name_prefix(
            default_client, pod_prefix="importer", namespace=source_dv.namespace,
        )
        importer_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=300)
        assert_selected_node_annotation(
            pvc=source_dv.pvc, pod=importer_pod, type_="source"
        )
        source_dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=300)
        with create_dv(
            source="pvc",
            dv_name="cnv-3516-target-dv",
            namespace=storage_ns.name,
            source_namespace=source_dv.namespace,
            source_pvc=source_dv.pvc.name,
            size="20Gi",
            storage_class=StorageClass.Types.HOSTPATH,
            volume_mode=DataVolume.VolumeMode.FILE,
        ) as target_dv:
            target_dv.pvc.wait(timeout=300)
            upload_target_pod = get_pod_by_name_prefix(
                default_client, pod_prefix="cdi-upload", namespace=storage_ns.name
            )
            upload_target_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=180)
            assert_selected_node_annotation(
                pvc=target_dv.pvc, pod=upload_target_pod, type_="target"
            )
            target_dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=600)
            with storage_utils.create_vm_from_dv(dv=target_dv) as vm:
                storage_utils.check_disk_count_in_vm(vm=vm)


@pytest.mark.polarion("CNV-3328")
def test_hostpath_import_scratch_dv_without_specify_node_wffc(
    skip_when_hpp_no_waitforfirstconsumer, storage_ns,
):
    """
    Check that in case of WaitForFirstConsumer binding mode, without annotating DV to a node,
    CDI import function needs scratch space works well.
    The PVC will have an annotation 'volume.kubernetes.io/selected-node' containing the node name
    where the pod is scheduled on.
    """
    with create_dv(
        source="http",
        dv_name="cnv-3328-dv",
        namespace=storage_ns.name,
        url=f"{get_images_external_http_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG_XZ}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=300)
        dv.importer_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=300)
        assert_selected_node_annotation(pvc=dv.pvc, pod=dv.importer_pod, type_="target")
        dv.scratch_pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=300
        )
        assert_selected_node_annotation(
            pvc=dv.scratch_pvc, pod=dv.importer_pod, type_="scratch"
        )
        dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=300)
