import os

import pytest
from ocp_resources.chaos_result import ChaosResult
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.service_account import ServiceAccount
from ocp_resources.utils import TimeoutSampler

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
    ChaosEngineFromFile,
    CmdProbe,
    EnvComponent,
    Experiment,
    K8SProbe,
)
from tests.chaos.utils.kraken_container import KrakenContainer
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_5SEC, Images
from utilities.infra import collect_resources_for_test, create_ns
from utilities.virt import CIRROS_IMAGE, VirtualMachineForTests, running_vm


@pytest.fixture()
def chaos_namespace():
    yield from create_ns(name=CHAOS_NAMESPACE)


@pytest.fixture()
def litmus_namespace():
    yield from create_ns(name=LITMUS_NAMESPACE)


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
        eviction=True,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def chaos_engine_from_yaml(request):
    experiment_name = request.param["experiment_name"]
    app_info_data = request.param["app_info"]
    components_data = request.param["components"]

    k8s_probes = create_k8s_probes(probes_data=request.param.get("k8s_probes"))
    cmd_probes = create_cmd_probes(probes_data=request.param.get("cmd_probes"))

    app_info = AppInfo(
        namespace=app_info_data["namespace"],
        label=app_info_data["label"],
        kind=app_info_data["kind"],
    )
    components = [
        EnvComponent(name=component["name"], value=component["value"])
        for component in components_data
    ]

    experiment = Experiment(
        name=experiment_name,
        probes=k8s_probes + cmd_probes,
        env_components=components,
    )
    chaos_engine = ChaosEngineFromFile(app_info=app_info, experiments=[experiment])
    chaos_engine.create_yaml()
    yield chaos_engine
    os.remove(f"{SCENARIOS_PATH_SOURCE}{CHAOS_ENGINE_FILE}")
    chaos_engine.clean_up()


def create_k8s_probes(probes_data):
    if probes_data:
        return [
            K8SProbe(
                name=probe["name"],
                mode=probe["mode"],
                probe_timeout=probe["probe_timeout"],
                interval=probe["interval"],
                retries=probe["retries"],
                group=probe.get("group"),
                version=probe.get("version"),
                resource=probe.get("resource"),
                namespace=probe.get("namespace"),
                operation=probe.get("operation"),
                label_selector=probe.get("label_selector"),
                field_selector=probe.get("field_selector"),
                data=probe.get("data"),
            )
            for probe in probes_data
        ]
    return []


def create_cmd_probes(probes_data):
    if probes_data:
        return [
            CmdProbe(
                name=probe["name"],
                mode=probe["mode"],
                probe_timeout=probe["probe_timeout"],
                interval=probe["interval"],
                retries=probe["retries"],
                command=probe["command"],
                comparator_type=probe["comparator_type"],
                comparator_criteria=probe["comparator_criteria"],
                comparator_value=probe["comparator_value"],
            )
            for probe in probes_data
        ]
    return []


@pytest.fixture()
def kraken_container(litmus_namespace):
    kraken_container = KrakenContainer()
    kraken_container.run()

    yield kraken_container
    collect_resources_for_test(
        resources_to_collect=[ChaosResult], namespace_name=litmus_namespace.name
    )


@pytest.fixture()
def running_chaos_engine(chaos_engine_from_yaml, kraken_container):
    chaos_engine_from_yaml.wait()
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: chaos_engine_from_yaml.experiments_status[
            chaos_engine_from_yaml.experiments[0].name
        ]["status"],
    )
    for sample in samples:
        if sample and sample == chaos_engine_from_yaml.Status.RUNNING:
            return chaos_engine_from_yaml
