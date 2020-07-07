# -*- coding: utf-8 -*-

"""
Hostpath Provisioner test suite
"""
import logging

import pytest
import tests.storage.utils as storage_utils
from pytest_testconfig import config as py_config
from resources.cluster_role import ClusterRole
from resources.cluster_role_binding import ClusterRoleBinding
from resources.daemonset import DaemonSet
from resources.datavolume import DataVolume
from resources.deployment import Deployment
from resources.hostpath_provisioner import HostPathProvisioner
from resources.persistent_volume_claim import PersistentVolumeClaim
from resources.pod import Pod
from resources.security_context_constraints import SecurityContextConstraints
from resources.service_account import ServiceAccount
from resources.storage_class import StorageClass
from utilities import console
from utilities.infra import Images
from utilities.storage import create_dv, get_images_external_http_server
from utilities.virt import wait_for_console


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


@pytest.fixture(scope="module")
def hpp_operator_deployment():
    LOGGER.debug("Use 'hpp_operator_deployment' fixture...")
    hpp_operator_deployment = Deployment(
        name="hostpath-provisioner-operator", namespace=py_config["hco_namespace"]
    )
    assert hpp_operator_deployment.exists
    return hpp_operator_deployment


@pytest.fixture(scope="module")
def skip_when_cdiconfig_scratch_no_hpp(skip_test_if_no_hpp_sc, cdi_config):
    LOGGER.debug("Use 'skip_when_cdiconfig_scratch_no_hpp' fixture...")
    if not (
        cdi_config.scratch_space_storage_class_from_status
        == StorageClass.Types.HOSTPATH
    ):
        pytest.skip(msg="scratchSpaceStorageClass of cdiconfig is not HPP")


@pytest.fixture(scope="module")
def hostpath_provisioner():
    LOGGER.debug("Use 'hostpath_provisioner' fixture...")
    yield HostPathProvisioner(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)


@pytest.fixture(scope="module")
def hpp_serviceaccount():
    LOGGER.debug("Use 'hpp_serviceaccount' fixture...")
    yield ServiceAccount(
        name="hostpath-provisioner-admin", namespace=py_config["hco_namespace"]
    )


@pytest.fixture(scope="module")
def hpp_scc():
    LOGGER.debug("Use 'hpp_scc' fixture...")
    yield SecurityContextConstraints(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)


@pytest.fixture(scope="module")
def hpp_clusterrole():
    LOGGER.debug("Use 'hpp_clusterrole' fixture...")
    yield ClusterRole(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)


@pytest.fixture(scope="module")
def hpp_clusterrolebinding():
    LOGGER.debug("Use 'hpp_clusterrolebinding' fixture...")
    yield ClusterRoleBinding(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)


@pytest.fixture(scope="module")
def hpp_daemonset():
    LOGGER.debug("Use 'hpp_daemonset' fixture...")
    yield DaemonSet(
        name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER,
        namespace=py_config["hco_namespace"],
    )


def verify_image_location_via_dv_pod_with_pvc(dv, worker_node):
    dv.wait()
    with storage_utils.PodWithPVC(
        namespace=dv.namespace,
        name=f"{dv.name}-pod",
        pvc_name=dv.pvc.name,
        volume_mode=py_config["default_volume_mode"],
    ) as pod:
        pod.wait_for_status(status="Running")
        LOGGER.debug("Check pod location...")
        assert pod.instance["spec"]["nodeName"] == worker_node.name
        LOGGER.debug("Check image location...")
        assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


def verify_image_location_via_dv_virt_launcher_pod(dv, worker_node):
    dv.wait()
    with storage_utils.create_vm_from_dv(dv=dv) as vm:
        vm.vmi.wait_until_running()
        v_pod = vm.vmi.virt_launcher_pod
        LOGGER.debug("Check pod location...")
        assert v_pod.instance["spec"]["nodeName"] == worker_node.name
        LOGGER.debug("Check image location...")
        assert "disk.img" in v_pod.execute(
            command=["ls", "-1", "/var/run/kubevirt-private/vmi-disks/dv-disk"]
        )


def assert_provision_on_node_annotation(pvc, node_name, type_):
    provision_on_node = "kubevirt.io/provisionOnNode"
    assert pvc.instance.metadata.annotations.get(provision_on_node) == node_name
    f"No '{provision_on_node}' annotation found on {type_} PVC"


def assert_selected_node_annotation(pvc, pod, type_):
    assert (
        pvc.selected_node == pod.instance.spec.nodeName
    ), f"No 'volume.kubernetes.io/selected-node' annotation found on {type_} PVC"


def get_pod_by_name_prefix(default_client, pod_prefix, namespace):
    pods = [
        pod
        for pod in Pod.get(dyn_client=default_client, namespace=namespace)
        if pod.name.startswith(pod_prefix)
    ]
    return pods[0]


@pytest.mark.polarion("CNV-2817")
def test_hostpath_pod_reference_pvc(skip_test_if_no_hpp_sc, namespace, worker_node1):
    """
    Check that after disk image is written to the PVC which has been provisioned on the specified node,
    Pod can use this image.
    """
    with create_dv(
        source="http",
        dv_name="cnv-2817",
        namespace=namespace.name,
        url=f"{get_images_external_http_server()}{Images.Fedora.DIR}/{Images.Fedora.FEDORA29_IMG}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="20Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
        hostpath_node=worker_node1.name,
    ) as dv:
        verify_image_location_via_dv_pod_with_pvc(dv=dv, worker_node=worker_node1)


@pytest.mark.polarion("CNV-3354")
def test_hpp_not_specify_node_immediate(skip_when_hpp_no_immediate, namespace):
    """
    Negative case
    Check that PVC should remain Pending when hostpath node was not specified
    and the volumeBindingMode of hostpath-provisioner StorageClass is 'Immediate'
    """
    with create_dv(
        source="http",
        dv_name="cnv-3354",
        namespace=namespace.name,
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
    skip_when_hpp_no_immediate, namespace, worker_node1
):
    """
    Check that the PVC will bound PV and DataVolume status becomes Succeeded once importer Pod finished importing
    when PVC is annotated to a specified node and the volumeBindingMode of hostpath-provisioner StorageClass is
    'Immediate'
    """
    with create_dv(
        source="http",
        dv_name="cnv-3228",
        namespace=namespace.name,
        url=f"{get_images_external_http_server()}{Images.Rhel.RHEL8_0_IMG}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="35Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
        hostpath_node=worker_node1.name,
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
    skip_when_hpp_no_immediate, namespace, dv_name, image_name, worker_node1,
):
    """
    Check that CDI importing from HTTP endpoint works well with hostpath-provisioner
    """
    with create_dv(
        source="http",
        dv_name=dv_name,
        namespace=namespace.name,
        content_type=DataVolume.ContentType.KUBEVIRT,
        url=f"{get_images_external_http_server()}{Images.Cirros.DIR}/{image_name}",
        size="500Mi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
        hostpath_node=worker_node1.name,
    ) as dv:
        verify_image_location_via_dv_virt_launcher_pod(dv=dv, worker_node=worker_node1)


@pytest.mark.polarion("CNV-3227")
def test_hpp_pvc_without_specify_node_waitforfirstconsumer(
    skip_when_hpp_no_waitforfirstconsumer, namespace,
):
    """
    Check that in the condition of the volumeBindingMode of hostpath-provisioner StorageClass is 'WaitForFirstConsumer',
    if you do not specify the node on the PVC, it will remain Pending.
    The PV will be created only and PVC get bound when the first Pod using this PVC is scheduled.
    """
    with PersistentVolumeClaim(
        name="cnv-3227",
        namespace=namespace.name,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
    ) as pvc:
        pvc.wait_for_status(
            status=pvc.Status.PENDING, timeout=60, stop_status=pvc.Status.BOUND
        )
        with storage_utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=DataVolume.VolumeMode.FILE,
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING, timeout=180)
            pvc.wait_for_status(status=pvc.Status.BOUND, timeout=60)
            assert pod.instance.spec.nodeName == pvc.selected_node


@pytest.mark.polarion("CNV-3280")
def test_hpp_pvc_specify_node_waitforfirstconsumer(
    skip_when_hpp_no_waitforfirstconsumer, namespace, worker_node1,
):
    """
    Check that kubevirt.io/provisionOnNode annotation works in WaitForFirstConsumer mode.
    Even in this mode, the annotation still causes an immediate bind on the specified node.
    """
    with PersistentVolumeClaim(
        name="cnv-3280",
        namespace=namespace.name,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        hostpath_node=worker_node1.name,
    ) as pvc:
        pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=60)
        assert_provision_on_node_annotation(
            pvc=pvc, node_name=worker_node1.name, type_="regular"
        )
        with storage_utils.PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=DataVolume.VolumeMode.FILE,
        ) as pod:
            pod.wait_for_status(status=Pod.Status.RUNNING, timeout=180)
            assert pod.instance.spec.nodeName == worker_node1.name


@pytest.mark.polarion("CNV-2771")
def test_hpp_upload_virtctl(
    skip_when_hpp_no_waitforfirstconsumer,
    skip_when_cdiconfig_scratch_no_hpp,
    namespace,
    tmpdir,
):
    """
    Check that upload disk image via virtcl tool works
    """
    local_name = f"{tmpdir}/{Images.Fedora.FEDORA29_IMG}"
    remote_name = f"{Images.Fedora.DIR}/{Images.Fedora.FEDORA29_IMG}"
    storage_utils.downloaded_image(remote_name=remote_name, local_name=local_name)
    pvc_name = "cnv-2771"
    virtctl_upload = storage_utils.virtctl_upload(
        namespace=namespace.name,
        image_path=local_name,
        pvc_size="25Gi",
        pvc_name=pvc_name,
        storage_class=StorageClass.Types.HOSTPATH,
        insecure=True,
    )
    LOGGER.debug(virtctl_upload)
    assert virtctl_upload
    pvc = PersistentVolumeClaim(namespace=namespace.name, name=pvc_name)
    assert pvc.bound()
    scratch_pvc = PersistentVolumeClaim(
        namespace=namespace.name, name=f"{pvc_name}-scratch"
    )
    pod = Pod(namespace=namespace.name, name=f"cdi-upload-{pvc.name}")
    assert (
        pvc.selected_node == pod.instance.spec.nodeName
        and scratch_pvc.selected_node == pod.instance.spec.nodeName
    ), "No 'volume.kubernetes.io/selected-node' annotation found on PVC"


@pytest.mark.polarion("CNV-2769")
def test_hostpath_upload_dv_with_token(
    skip_test_if_no_hpp_sc,
    skip_when_cdiconfig_scratch_no_hpp,
    namespace,
    tmpdir,
    worker_node1,
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
        namespace=namespace.name,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        hostpath_node=worker_node1.name,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=180)
        storage_utils.upload_token_request(
            storage_ns_name=dv.namespace, pvc_name=dv.pvc.name, data=local_name
        )
        dv.wait()
        verify_image_location_via_dv_pod_with_pvc(dv=dv, worker_node=worker_node1)


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
    skip_when_cdiconfig_scratch_no_hpp,
    hpp_storage_class,
    namespace,
    dv_name,
    url,
    worker_node1,
):
    """
    Check that when importing image from public registry with kubevirt.io/provisionOnNode annotation works well.
    On WaitForFirstConsumer Mode, the 'volume.kubernetes.io/selected-node' annotation will be added to scratch PVC.
    """
    with create_dv(
        source="registry",
        dv_name=dv_name,
        namespace=namespace.name,
        url=url,
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        hostpath_node=worker_node1.name,
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
            pvc=dv.pvc, node_name=worker_node1.name, type_="import"
        )
        dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=300)
        verify_image_location_via_dv_virt_launcher_pod(dv=dv, worker_node=worker_node1)


@pytest.mark.parametrize(
    "data_volume_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-3516-source-dv",
                "image": f"{Images.Fedora.DIR}/{Images.Fedora.FEDORA30_IMG}",
                "dv_size": "10Gi",
                "storage_class": StorageClass.Types.HOSTPATH,
            },
            marks=(pytest.mark.polarion("CNV-3516")),
        ),
    ],
    indirect=True,
)
def test_hostpath_clone_dv_without_annotation_wffc(
    skip_when_hpp_no_waitforfirstconsumer,
    default_client,
    namespace,
    data_volume_scope_function,
):
    """
    Check that in case of WaitForFirstConsumer binding mode, without annotating the source/target DV to a node,
    CDI clone function works well. The PVCs will have an annotation 'volume.kubernetes.io/selected-node' containing
    the node name where the pod is scheduled on.
    """
    with create_dv(
        source="pvc",
        dv_name="cnv-3516-target-dv",
        namespace=namespace.name,
        source_namespace=data_volume_scope_function.namespace,
        source_pvc=data_volume_scope_function.pvc.name,
        size="10Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as target_dv:
        target_dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND)
        upload_target_pod = get_pod_by_name_prefix(
            default_client=default_client,
            pod_prefix="cdi-upload",
            namespace=namespace.name,
        )
        upload_target_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=180)
        assert_selected_node_annotation(
            pvc=target_dv.pvc, pod=upload_target_pod, type_="target"
        )
        target_dv.wait(timeout=300)
        with storage_utils.create_vm_from_dv(dv=target_dv, vm_name="fedora-vm") as vm:
            wait_for_console(vm=vm, console_impl=console.Fedora)


@pytest.mark.polarion("CNV-3328")
def test_hostpath_import_scratch_dv_without_specify_node_wffc(
    skip_when_hpp_no_waitforfirstconsumer,
    skip_when_cdiconfig_scratch_no_hpp,
    namespace,
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
        namespace=namespace.name,
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


@pytest.mark.polarion("CNV-2770")
def test_hostpath_clone_dv_with_annotation(
    skip_test_if_no_hpp_sc, namespace, worker_node1
):
    """
    Check that on WaitForFirstConsumer or Immediate binding mode,
    if the source/target DV is annotated to a specified node, CDI clone function works well.
    The PVCs will have an annotation 'kubevirt.io/provisionOnNode: <specified_node_name>'
    and bound immediately.
    """
    with create_dv(
        source="http",
        dv_name="cnv-2770-source-dv",
        namespace=namespace.name,
        content_type=DataVolume.ContentType.KUBEVIRT,
        url=f"{get_images_external_http_server()}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
        hostpath_node=worker_node1.name,
    ) as source_dv:
        source_dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=300)
        assert_provision_on_node_annotation(
            pvc=source_dv.pvc, node_name=worker_node1.name, type_="import"
        )
        with create_dv(
            source="pvc",
            dv_name="cnv-2770-target-dv",
            namespace=namespace.name,
            size="1Gi",
            storage_class=StorageClass.Types.HOSTPATH,
            hostpath_node=worker_node1.name,
            volume_mode=DataVolume.VolumeMode.FILE,
            source_namespace=source_dv.namespace,
            source_pvc=source_dv.pvc.name,
        ) as target_dv:
            target_dv.wait_for_status(status=DataVolume.Status.SUCCEEDED, timeout=600)
            assert_provision_on_node_annotation(
                pvc=target_dv.pvc, node_name=worker_node1.name, type_="target"
            )
            with storage_utils.create_vm_from_dv(dv=target_dv) as vm:
                storage_utils.check_disk_count_in_vm(vm=vm)


@pytest.mark.polarion("CNV-3279")
def test_hpp_cr(skip_test_if_no_hpp_sc, hostpath_provisioner):
    assert hostpath_provisioner.exists
    assert hostpath_provisioner.volume_path == "/var/hpvolumes"


@pytest.mark.polarion("CNV-3279")
def test_hpp_serviceaccount(skip_test_if_no_hpp_sc, hpp_serviceaccount):
    assert hpp_serviceaccount.exists


@pytest.mark.polarion("CNV-3279")
def test_hpp_scc(skip_test_if_no_hpp_sc, hpp_scc):
    assert hpp_scc.exists
    assert (
        hpp_scc.instance.users[0]
        == "system:serviceaccount:openshift-cnv:hostpath-provisioner-admin"
    ), "No 'hostpath-provisioner-admin' SA attached to 'hostpath-provisioner' SCC"


@pytest.mark.polarion("CNV-3279")
def test_hpp_clusterrole_and_clusterrolebinding(
    skip_test_if_no_hpp_sc, hpp_clusterrole, hpp_clusterrolebinding
):
    assert hpp_clusterrole.exists
    assert hpp_clusterrole.instance["metadata"]["name"] == "hostpath-provisioner"

    assert hpp_clusterrolebinding.exists
    assert (
        hpp_clusterrolebinding.instance["subjects"][0]["name"]
        == "hostpath-provisioner-admin"
    )


@pytest.mark.polarion("CNV-3279")
def test_hpp_daemonset(skip_test_if_no_hpp_sc, hpp_daemonset):
    assert hpp_daemonset.exists
    assert (
        hpp_daemonset.instance.status.numberReady
        == hpp_daemonset.instance.status.desiredNumberScheduled
    )


@pytest.mark.polarion("CNV-3279")
def test_hpp_operator_pod(skip_test_if_no_hpp_sc, default_client):
    hpp_operator_pod = get_pod_by_name_prefix(
        default_client=default_client,
        pod_prefix="hostpath-provisioner-operator",
        namespace=py_config["hco_namespace"],
    )
    assert hpp_operator_pod.status == Pod.Status.RUNNING


@pytest.mark.destructive
@pytest.mark.polarion("CNV-3277")
def test_hpp_operator_recreate_after_deletion(
    skip_test_if_no_hpp_sc, hpp_operator_deployment
):
    """
    Check that Hostpath-provisioner operator will be created again by HCO after its deletion.
    The Deployment is deleted, then its RepliceSet and Pod will be deleted and created again.
    """
    hpp_operator_deployment.delete()
    hpp_operator_deployment.wait_until_avail_replicas(timeout=300)
