# -*- coding: utf-8 -*-

"""
Hostpath Provisioner test suite
"""
import logging
from multiprocessing.pool import ThreadPool

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.configmap import ConfigMap
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.hostpath_provisioner import HostPathProvisioner
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.replicaset import ReplicaSet
from ocp_resources.resource import Resource
from ocp_resources.role import Role
from ocp_resources.role_binding import RoleBinding
from ocp_resources.security_context_constraints import SecurityContextConstraints
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount
from ocp_resources.storage_class import StorageClass
from ocp_resources.template import Template
from ocp_resources.utils import TimeoutSampler
from pytest_testconfig import config as py_config

import tests.storage.utils as storage_utils
from utilities.constants import (
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_10MIN,
    TIMEOUT_20SEC,
    TIMEOUT_30SEC,
    Images,
)
from utilities.infra import get_pod_by_name_prefix
from utilities.storage import (
    PodWithPVC,
    create_dv,
    downloaded_image,
    get_images_server_url,
    get_storage_class_dict_from_matrix,
    sc_volume_binding_mode_is_wffc,
    virtctl_upload_dv,
)
from utilities.virt import VirtualMachineForTestsFromTemplate, running_vm


LOGGER = logging.getLogger(__name__)
HPP_OPERATOR = "hostpath-provisioner-operator"

pytestmark = pytest.mark.usefixtures("skip_if_hpp_not_in_sc_options")


def verify_hpp_app_label(hpp_resources, cnv_version):
    for resource in hpp_resources:
        if resource.kind == "ServiceAccount" and resource.name == HPP_OPERATOR:
            continue
        elif (
            resource.kind == "ConfigMap"
            and resource.name == "hostpath-provisioner-operator-lock"
        ):
            continue
        else:
            assert (
                resource.labels[f"{Resource.ApiGroup.APP_KUBERNETES_IO}/component"]
                == "storage"
            ), f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/component for {resource.name}"
            assert (
                resource.labels[f"{Resource.ApiGroup.APP_KUBERNETES_IO}/part-of"]
                == "hyperconverged-cluster"
            ), f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/part-of for {resource.name}"
            assert (
                resource.labels[f"{Resource.ApiGroup.APP_KUBERNETES_IO}/version"]
                == f"v{cnv_version}"
            ), f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/version for {resource.name}"
            if resource.name.startswith(HPP_OPERATOR):
                assert (
                    resource.labels[f"{resource.ApiGroup.APP_KUBERNETES_IO}/managed-by"]
                    == "olm"
                ), f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by for {resource.name}"
            else:
                assert (
                    resource.labels[f"{resource.ApiGroup.APP_KUBERNETES_IO}/managed-by"]
                    == HPP_OPERATOR
                ), f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by for {resource.name}"


@pytest.fixture(scope="module")
def skip_when_hpp_no_immediate(skip_test_if_no_hpp_sc, hpp_storage_class):
    if (
        not hpp_storage_class.instance["volumeBindingMode"]
        == StorageClass.VolumeBindingMode.Immediate
    ):
        pytest.skip(msg="Test only run when volumeBindingMode is Immediate")


@pytest.fixture(scope="module")
def hpp_operator_deployment(hco_namespace):
    hpp_operator_deployment = Deployment(
        name=HPP_OPERATOR, namespace=hco_namespace.name
    )
    assert hpp_operator_deployment.exists
    return hpp_operator_deployment


@pytest.fixture(scope="module")
def skip_when_cdiconfig_scratch_no_hpp(skip_test_if_no_hpp_sc, cdi_config):
    if not (
        cdi_config.scratch_space_storage_class_from_status
        == StorageClass.Types.HOSTPATH
    ):
        pytest.skip(msg="scratchSpaceStorageClass of cdiconfig is not HPP")


@pytest.fixture(scope="module")
def hpp_serviceaccount(hco_namespace):
    yield ServiceAccount(
        name="hostpath-provisioner-admin", namespace=hco_namespace.name
    )


@pytest.fixture(scope="module")
def hpp_scc():
    yield SecurityContextConstraints(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)


@pytest.fixture(scope="module")
def hpp_clusterrole():
    yield ClusterRole(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)


@pytest.fixture(scope="module")
def hpp_clusterrolebinding():
    yield ClusterRoleBinding(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)


@pytest.fixture(scope="module")
def hpp_operator_pod(admin_client, hco_namespace):
    yield get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=HPP_OPERATOR,
        namespace=hco_namespace.name,
    )


@pytest.fixture()
def dv_kwargs(request, namespace, worker_node1):
    storage_class_dict = get_storage_class_dict_from_matrix(
        storage_class=StorageClass.Types.HOSTPATH
    )
    storage_class = [*storage_class_dict][0]
    dv_kwargs = {
        "dv_name": request.param.get("name"),
        "namespace": namespace.name,
        "url": request.param.get(
            "url",
            f"{get_images_server_url(schema='http')}{py_config['latest_fedora_os_dict']['image_path']}",
        ),
        "size": request.param.get("size", Images.Fedora.DEFAULT_DV_SIZE),
        "storage_class": storage_class,
        "volume_mode": storage_class_dict[storage_class]["volume_mode"],
        "hostpath_node": worker_node1.name,
    }

    return dv_kwargs


def verify_image_location_via_dv_pod_with_pvc(dv, worker_node_name):
    dv.wait()
    with PodWithPVC(
        namespace=dv.namespace,
        name=f"{dv.name}-pod",
        pvc_name=dv.pvc.name,
        volume_mode=dv.volume_mode,
    ) as pod:
        pod.wait_for_status(status="Running")
        LOGGER.debug("Check pod location...")
        assert pod.instance["spec"]["nodeName"] == worker_node_name
        LOGGER.debug("Check image location...")
        assert "disk.img" in pod.execute(command=["ls", "-1", "/pvc"])


def verify_image_location_via_dv_virt_launcher_pod(dv, worker_node_name):
    dv.wait()
    with storage_utils.create_vm_from_dv(dv=dv) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False, wait_for_interfaces=False)
        v_pod = vm.vmi.virt_launcher_pod
        LOGGER.debug("Check pod location...")
        assert v_pod.instance["spec"]["nodeName"] == worker_node_name
        LOGGER.debug("Check image location...")
        assert "disk.img" in v_pod.execute(
            command=["ls", "-1", "/var/run/kubevirt-private/vmi-disks/dv-disk"]
        )


def assert_provision_on_node_annotation(pvc, node_name, type_):
    provision_on_node = "kubevirt.io/provisionOnNode"
    assert pvc.instance.metadata.annotations.get(provision_on_node) == node_name
    f"No '{provision_on_node}' annotation found on {type_} PVC / node names differ"


def assert_selected_node_annotation(pvc_node_name, pod_node_name, type_="source"):
    assert (
        pvc_node_name == pod_node_name
    ), f"No 'volume.kubernetes.io/selected-node' annotation found on {type_} PVC / node names differ"


def _get_pod_and_scratch_pvc(dyn_client, namespace, pod_prefix, pvc_suffix):
    pvcs = list(PersistentVolumeClaim.get(dyn_client=dyn_client, namespace=namespace))
    matched_pvcs = [pvc for pvc in pvcs if pvc.name.endswith(pvc_suffix)]
    matched_pod = get_pod_by_name_prefix(
        dyn_client=dyn_client, pod_prefix=pod_prefix, namespace=namespace
    )
    return {
        "pod": matched_pod,
        "pvc": matched_pvcs[0] if matched_pvcs else None,
    }


def get_pod_and_scratch_pvc_nodes(dyn_client, namespace):
    """
    Returns scratch pvc and pod nodes using sampling.
    This is essential in order to get hold of the resources before they are finished and not accessible.

    Args:
        namespace: namespace to search in
        dyn_client: open connection to remote cluster
    """
    LOGGER.info("Waiting for cdi-upload worker pod and scratch pvc")
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_30SEC,
        sleep=5,
        func=_get_pod_and_scratch_pvc,
        dyn_client=dyn_client,
        namespace=namespace,
        pod_prefix="cdi-upload",
        pvc_suffix="scratch",
    )
    for sample in sampler:
        pod = sample.get("pod")
        pvc = sample.get("pvc")
        if pod and pvc:
            pod_node = pod.instance.spec.nodeName
            pvc_node = pvc.selected_node
            if pod_node and pvc_node:
                LOGGER.info("Found cdi-upload worker pod and scratch pvc")
                return {
                    "pod_node": pod_node,
                    "scratch_pvc_node": pvc_node,
                }


@pytest.mark.polarion("CNV-2817")
@pytest.mark.parametrize(
    "dv_kwargs",
    [
        pytest.param(
            {
                "name": "cnv-2817",
            },
            marks=(pytest.mark.polarion("CNV-2327")),
        ),
    ],
    indirect=True,
)
def test_hostpath_pod_reference_pvc(skip_test_if_no_hpp_sc, namespace, dv_kwargs):
    """
    Check that after disk image is written to the PVC which has been provisioned on the specified node,
    Pod can use this image.
    """
    if sc_volume_binding_mode_is_wffc(sc=StorageClass.Types.HOSTPATH):
        dv_kwargs.pop("hostpath_node")
    with create_dv(**dv_kwargs) as dv:
        verify_image_location_via_dv_pod_with_pvc(
            dv=dv, worker_node_name=dv.pvc.selected_node or dv.hostpath_node
        )


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
        url=f"{get_images_server_url(schema='http')}{Images.Windows.WIN16_IMG}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="35Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.wait_for_status(
            status=dv.Status.PENDING,
            timeout=TIMEOUT_2MIN,
            stop_status=dv.Status.SUCCEEDED,
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
        url=f"{get_images_server_url(schema='http')}{Images.Rhel.RHEL8_0_IMG}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="35Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
        hostpath_node=worker_node1.name,
    ) as dv:
        dv.wait(timeout=TIMEOUT_10MIN)


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
    skip_when_hpp_no_immediate,
    namespace,
    dv_name,
    image_name,
    worker_node1,
):
    """
    Check that CDI importing from HTTP endpoint works well with hostpath-provisioner
    """
    with create_dv(
        source="http",
        dv_name=dv_name,
        namespace=namespace.name,
        content_type=DataVolume.ContentType.KUBEVIRT,
        url=f"{get_images_server_url(schema='http')}{Images.Cirros.DIR}/{image_name}",
        size="500Mi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
        hostpath_node=worker_node1.name,
    ) as dv:
        verify_image_location_via_dv_virt_launcher_pod(
            dv=dv, worker_node_name=worker_node1.name
        )


@pytest.mark.polarion("CNV-3227")
def test_hpp_pvc_without_specify_node_waitforfirstconsumer(
    skip_when_hpp_no_waitforfirstconsumer,
    namespace,
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
            status=pvc.Status.PENDING,
            timeout=TIMEOUT_1MIN,
            stop_status=pvc.Status.BOUND,
        )
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=pvc.volume_mode,
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING, timeout=TIMEOUT_3MIN)
            pvc.wait_for_status(status=pvc.Status.BOUND, timeout=TIMEOUT_1MIN)
            assert pod.instance.spec.nodeName == pvc.selected_node


@pytest.mark.polarion("CNV-3280")
def test_hpp_pvc_specify_node_immediate(
    skip_when_hpp_no_immediate,
    namespace,
    worker_node1,
):
    """
    Check that kubevirt.io/provisionOnNode annotation works in Immediate mode.
    The annotation causes an immediate bind on the specified node.
    """
    with PersistentVolumeClaim(
        name="cnv-3280",
        namespace=namespace.name,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        hostpath_node=worker_node1.name,
    ) as pvc:
        pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_1MIN
        )
        assert_provision_on_node_annotation(
            pvc=pvc, node_name=worker_node1.name, type_="regular"
        )
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            volume_mode=pvc.volume_mode,
        ) as pod:
            pod.wait_for_status(status=Pod.Status.RUNNING, timeout=TIMEOUT_3MIN)
            assert pod.instance.spec.nodeName == worker_node1.name


@pytest.mark.polarion("CNV-2771")
def test_hpp_upload_virtctl(
    skip_when_hpp_no_waitforfirstconsumer,
    skip_when_cdiconfig_scratch_no_hpp,
    admin_client,
    namespace,
    tmpdir,
):
    """
    Check that upload disk image via virtctl tool works
    """
    latest_fedora_image = py_config["latest_fedora_os_dict"]["image_name"]
    local_name = f"{tmpdir}/{latest_fedora_image}"
    remote_name = f"{Images.Fedora.DIR}/{latest_fedora_image}"
    downloaded_image(remote_name=remote_name, local_name=local_name)
    pvc_name = "cnv-2771"

    # Get pod and scratch pvc nodes, before they are inaccessible
    thread_pool = ThreadPool(processes=1)
    async_result = thread_pool.apply_async(
        func=get_pod_and_scratch_pvc_nodes,
        kwds={"dyn_client": admin_client, "namespace": namespace.name},
    )
    # Start virtctl upload process, meanwhile, resources are sampled
    with virtctl_upload_dv(
        namespace=namespace.name,
        name=pvc_name,
        size="25Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        image_path=local_name,
        insecure=True,
    ) as virtctl_upload:
        return_val = async_result.get()  # get return value from side thread
        assert virtctl_upload
        pvc = PersistentVolumeClaim(name=pvc_name, namespace=namespace.name)
        assert pvc.bound()
        assert all(
            node == return_val.get("pod_node")
            for node in (pvc.selected_node, return_val.get("scratch_pvc_node"))
        ), "No 'volume.kubernetes.io/selected-node' annotation found on PVC / node names differ"


@pytest.mark.polarion("CNV-2769")
def test_hostpath_upload_dv_with_token(
    skip_test_if_no_hpp_sc,
    skip_when_cdiconfig_scratch_no_hpp,
    skip_when_hpp_no_waitforfirstconsumer,
    namespace,
    tmpdir,
):
    dv_name = "cnv-2769"
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    remote_name = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
    downloaded_image(
        remote_name=remote_name,
        local_name=local_name,
    )
    with create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=namespace.name,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_3MIN)
        storage_utils.upload_token_request(
            storage_ns_name=dv.namespace, pvc_name=dv.pvc.name, data=local_name
        )
        dv.wait()
        verify_image_location_via_dv_pod_with_pvc(
            dv=dv, worker_node_name=dv.pvc.selected_node
        )


@pytest.mark.parametrize(
    ("dv_name", "url"),
    [
        pytest.param(
            "cnv-3326-quay",
            f"docker://quay.io/kubevirt/{Images.Cirros.DISK_DEMO}",
            marks=(pytest.mark.polarion("CNV-3326")),
        ),
    ],
)
def test_hostpath_registry_import_dv(
    admin_client,
    skip_when_hpp_no_waitforfirstconsumer,
    skip_when_cdiconfig_scratch_no_hpp,
    hpp_storage_class,
    namespace,
    dv_name,
    url,
):
    """
    Check that when importing image from public registry with WFFC binding mode
    and without kubevirt.io/provisionOnNode annotation works well.
    The 'volume.kubernetes.io/selected-node' annotation will be added to scratch PVC.
    """
    with create_dv(
        source="registry",
        dv_name=dv_name,
        namespace=namespace.name,
        url=url,
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as dv:
        dv.scratch_pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_5MIN
        )
        importer_pod = storage_utils.get_importer_pod(
            dyn_client=admin_client, namespace=dv.namespace
        )
        importer_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=TIMEOUT_5MIN)
        assert_selected_node_annotation(
            pvc_node_name=dv.scratch_pvc.selected_node,
            pod_node_name=importer_pod.instance.spec.nodeName,
            type_="scratch",
        )
        dv.wait_for_status(status=dv.Status.SUCCEEDED, timeout=TIMEOUT_5MIN)
        verify_image_location_via_dv_virt_launcher_pod(
            dv=dv, worker_node_name=dv.pvc.selected_node
        )


@pytest.mark.parametrize(
    "data_volume_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-3516-source-dv",
                "image": py_config["latest_fedora_os_dict"]["image_path"],
                "dv_size": Images.Fedora.DEFAULT_DV_SIZE,
                "storage_class": StorageClass.Types.HOSTPATH,
            },
            marks=(pytest.mark.polarion("CNV-3516")),
        ),
    ],
    indirect=True,
)
def test_hostpath_clone_dv_without_annotation_wffc(
    skip_when_hpp_no_waitforfirstconsumer,
    admin_client,
    namespace,
    data_volume_scope_function,
):
    """
    Check that in case of WaitForFirstConsumer binding mode, without annotating the source/target DV to a node,
    CDI clone function works well. The PVCs will have an annotation 'volume.kubernetes.io/selected-node' containing
    the node name where the pod is scheduled on.
    """
    dv_name = "cnv-3516-target-dv"
    with create_dv(
        source="pvc",
        dv_name=dv_name,
        namespace=namespace.name,
        source_namespace=data_volume_scope_function.namespace,
        source_pvc=data_volume_scope_function.pvc.name,
        size=data_volume_scope_function.size,
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as target_dv:
        upload_target_pod = None
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_20SEC,
            sleep=1,
            func=lambda: list(
                Pod.get(
                    dyn_client=admin_client,
                    namespace=namespace.name,
                    name=f"cdi-upload-{dv_name}",
                )
            ),
        ):
            if sample:
                upload_target_pod = sample[0]
                break

        upload_target_pod.wait_for_status(
            status=Pod.Status.RUNNING, timeout=TIMEOUT_3MIN
        )
        assert_selected_node_annotation(
            pvc_node_name=target_dv.pvc.selected_node,
            pod_node_name=upload_target_pod.instance.spec.nodeName,
            type_="target",
        )
        target_dv.wait(timeout=TIMEOUT_5MIN)
        with VirtualMachineForTestsFromTemplate(
            name="fedora-vm",
            namespace=namespace.name,
            client=admin_client,
            labels=Template.generate_template_labels(
                **py_config["latest_fedora_os_dict"]["template_labels"]
            ),
            existing_data_volume=target_dv,
        ) as vm:
            running_vm(vm=vm)
            vm.ssh_exec.executor().is_connective()


@pytest.mark.polarion("CNV-2770")
def test_hostpath_clone_dv_with_annotation(
    skip_test_if_no_hpp_sc, skip_when_hpp_no_immediate, namespace, worker_node1
):
    """
    Check that on Immediate binding mode,
    if the source/target DV is annotated to a specified node, CDI clone function works well.
    The PVCs will have an annotation 'kubevirt.io/provisionOnNode: <specified_node_name>'
    and bound immediately.
    """
    with create_dv(
        source="http",
        dv_name="cnv-2770-source-dv",
        namespace=namespace.name,
        content_type=DataVolume.ContentType.KUBEVIRT,
        url=f"{get_images_server_url(schema='http')}{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
        size="1Gi",
        storage_class=StorageClass.Types.HOSTPATH,
        volume_mode=DataVolume.VolumeMode.FILE,
        hostpath_node=worker_node1.name,
    ) as source_dv:
        source_dv.wait_for_status(
            status=DataVolume.Status.SUCCEEDED, timeout=TIMEOUT_5MIN
        )
        assert_provision_on_node_annotation(
            pvc=source_dv.pvc, node_name=worker_node1.name, type_="import"
        )
        with create_dv(
            source="pvc",
            dv_name="cnv-2770-target-dv",
            namespace=namespace.name,
            size=source_dv.size,
            storage_class=StorageClass.Types.HOSTPATH,
            hostpath_node=worker_node1.name,
            volume_mode=DataVolume.VolumeMode.FILE,
            source_namespace=source_dv.namespace,
            source_pvc=source_dv.pvc.name,
        ) as target_dv:
            target_dv.wait_for_status(
                status=DataVolume.Status.SUCCEEDED, timeout=TIMEOUT_10MIN
            )
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
def test_hpp_operator_pod(skip_test_if_no_hpp_sc, hpp_operator_pod):
    assert (
        hpp_operator_pod.status == Pod.Status.RUNNING
    ), f"HPP operator pod {hpp_operator_pod.name} is not running"


@pytest.mark.destructive
@pytest.mark.polarion("CNV-3277")
def test_hpp_operator_recreate_after_deletion(
    skip_test_if_no_hpp_sc, hpp_operator_deployment, hpp_storage_class
):
    """
    Check that Hostpath-provisioner operator will be created again by HCO after its deletion.
    The Deployment is deleted, then its RepliceSet and Pod will be deleted and created again.
    """
    pre_delete_binding_mode = hpp_storage_class.instance["volumeBindingMode"]
    hpp_operator_deployment.delete()
    hpp_operator_deployment.wait_for_replicas(timeout=TIMEOUT_5MIN)
    assert (
        pre_delete_binding_mode == hpp_storage_class.instance["volumeBindingMode"]
    ), "Pre delete binding mode differs from post delete"


@pytest.mark.polarion("CNV-6097")
def test_hpp_operator_scc(skip_test_if_no_hpp_sc, hpp_scc, hpp_operator_pod):
    assert hpp_scc.exists, f"scc {hpp_scc.name} is not existed"
    hpp_scc_capabilities = sorted(hpp_scc.instance.requiredDropCapabilities)
    hpp_pod_capabilities = sorted(
        hpp_operator_pod.instance.spec["containers"][0]["securityContext"][
            "capabilities"
        ]["drop"]
    )
    user_id = hpp_operator_pod.instance.spec["containers"][0]["securityContext"][
        "runAsUser"
    ]
    assert hpp_scc_capabilities == hpp_pod_capabilities
    assert (
        type(user_id) == int and len(str(user_id)) == 10
    ), f"Container image is not runAsUser with user id {user_id}"


@pytest.mark.parametrize(
    "hpp_resources",
    [
        pytest.param(
            Pod,
            marks=(pytest.mark.polarion("CNV-7204")),
            id="hpp-pods",
        ),
        pytest.param(
            ServiceAccount,
            marks=(pytest.mark.polarion("CNV-7205")),
            id="hpp-service-accounts",
        ),
        pytest.param(
            Service,
            marks=(pytest.mark.polarion("CNV-7206")),
            id="hpp-service",
        ),
        pytest.param(
            Deployment,
            marks=(pytest.mark.polarion("CNV-7213")),
            id="hpp-deployment",
        ),
        pytest.param(
            ReplicaSet,
            marks=(pytest.mark.polarion("CNV-7214")),
            id="hpp-replicatset",
        ),
        pytest.param(
            CustomResourceDefinition,
            marks=(pytest.mark.polarion("CNV-7211")),
            id="hpp-crd",
        ),
        pytest.param(
            Role,
            marks=(pytest.mark.polarion("CNV-7212")),
            id="hpp-role",
        ),
        pytest.param(
            RoleBinding,
            marks=(pytest.mark.polarion("CNV-7209")),
            id="hpp-role-binding",
        ),
        pytest.param(
            ClusterRole,
            marks=(pytest.mark.polarion("CNV-7210")),
            id="hpp-cluster-role",
        ),
        pytest.param(
            ClusterRoleBinding,
            marks=(pytest.mark.polarion("CNV-7208")),
            id="hpp-cluster-role-binding",
        ),
        pytest.param(
            ConfigMap,
            marks=(pytest.mark.polarion("CNV-7207")),
            id="hpp-configmap",
        ),
    ],
    indirect=True,
)
def test_verify_hpp_res_app_label(
    skip_if_post_cnv_upgrade_cluster_and_labels_bug_not_closed,
    hpp_resources,
    cnv_current_version,
):
    verify_hpp_app_label(hpp_resources=hpp_resources, cnv_version=cnv_current_version)
