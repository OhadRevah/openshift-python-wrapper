import os

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.namespace import Namespace
from ocp_resources.service_account import ServiceAccount

from tests.chaos.constants import (
    CHAOS_ENGINE_FILE,
    CHAOS_NAMESPACE,
    LITMUS_NAMESPACE,
    LITMUS_SERVICE_ACCOUNT,
    SCENARIOS_PATH_SOURCE,
    VM_LABEL,
)
from tests.chaos.utils.chaos_engine import (
    AppInfo,
    ChaosEngineFile,
    EnvComponent,
    Experiment,
    Probe,
)
from tests.chaos.utils.kraken_container import KrakenContainer
from utilities.constants import TIMEOUT_5MIN, Images
from utilities.virt import CIRROS_IMAGE, VirtualMachineForTests, running_vm


@pytest.fixture()
def chaos_namespace():
    with Namespace(
        name=CHAOS_NAMESPACE,
    ) as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE, timeout=TIMEOUT_5MIN)
        yield ns


@pytest.fixture()
def litmus_namespace():
    with Namespace(name=LITMUS_NAMESPACE) as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE, timeout=TIMEOUT_5MIN)
        yield ns


@pytest.fixture()
def litmus_service_account(litmus_namespace):
    with ServiceAccount(
        name=LITMUS_SERVICE_ACCOUNT, namespace=litmus_namespace.name
    ) as sa:
        yield sa


@pytest.fixture()
def cluster_role_pod_delete(litmus_service_account):
    with ClusterRole(
        name=litmus_service_account.name,
        api_groups=[
            "",
            "apps",
            "batch",
            "extensions",
            "litmuschaos.io",
            "openebs.io",
            "storage.k8s.io",
            "kubevirt.io",
        ],
        permissions_to_resources=[
            "nodes",
            "chaosengines",
            "chaosexperiments",
            "chaosresults",
            "configmaps",
            "cstorpools",
            "cstorvolumereplicas",
            "daemonsets",
            "deployments",
            "events",
            "jobs",
            "persistentvolumeclaims",
            "persistentvolumes",
            "pods",
            "pods/eviction",
            "pods/exec",
            "pods/log",
            "replicasets",
            "secrets",
            "services",
            "statefulsets",
            "storageclasses",
            "virtualmachineinstances",
        ],
        verbs=["create", "delete", "get", "list", "patch", "update"],
    ) as cluster_role:
        yield cluster_role


@pytest.fixture()
def litmus_cluster_role_binding(litmus_namespace, litmus_service_account):
    with ClusterRoleBinding(
        name=litmus_service_account.name,
        cluster_role=litmus_service_account.name,
        subjects=[
            {
                "kind": "ServiceAccount",
                "name": litmus_service_account.name,
                "namespace": litmus_namespace.name,
            }
        ],
    ) as cluster_role_binding:
        yield cluster_role_binding


@pytest.fixture()
def vm_cirros_chaos(admin_client, chaos_namespace):
    with VirtualMachineForTests(
        client=admin_client,
        name="vm-chaos",
        namespace=chaos_namespace.name,
        image=CIRROS_IMAGE,
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
        additional_labels=VM_LABEL,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def chaos_engine_yaml(request):
    experiment_name = request.param["experiment_name"]
    app_info_data = request.param["app_info"]
    probes_data = request.param["probes"]
    components_data = request.param["components"]

    app_info = AppInfo(
        namespace=app_info_data["namespace"],
        label=app_info_data["label"],
        kind=app_info_data["kind"],
    )
    components = [
        EnvComponent(name=component["name"], value=component["value"])
        for component in components_data
    ]
    probes = [
        Probe(
            name=probe["name"],
            probe_type=probe["type"],
            mode=probe["mode"],
            group=probe["group"],
            version=probe["version"],
            resource=probe["resource"],
            namespace=probe["namespace"],
            label_selector=probe["label_selector"],
            operation=probe["operation"],
            probe_timeout=probe["probe_timeout"],
            interval=probe["interval"],
            retries=probe["retries"],
        )
        for probe in probes_data
    ]
    experiment = Experiment(
        name=experiment_name, probes=probes, env_components=components
    )
    chaos_engine = ChaosEngineFile(app_info=app_info, experiments=[experiment])
    chaos_engine.create_yaml()
    yield
    os.remove(f"{SCENARIOS_PATH_SOURCE}{CHAOS_ENGINE_FILE}")
    chaos_engine.clean_up()


@pytest.fixture()
def kraken_container():
    kraken_container = KrakenContainer()
    kraken_container.run()
    yield kraken_container
