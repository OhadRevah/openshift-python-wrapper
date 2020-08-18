import logging
import os
import threading
import time
from datetime import datetime

import docker
from pytest_testconfig import py_config
from resources.hyperconverged import HyperConverged
from resources.node import Node
from resources.virtual_machine import VirtualMachineInstanceMigration


LOGGER = logging.getLogger(__name__)


class KrakenScenario:
    def __init__(self, scenario):
        self.scenario = scenario
        self.client = docker.from_env()
        self.yaml_dir = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "kraken-manifests"
        )

    def run_scenario(self):
        name = f"kraken-{self.scenario}-{datetime.now().strftime('%d-%m-%Y-%H-%M-%S')}"
        config_path = os.path.join(self.yaml_dir, "config.yaml")
        scenario_path = os.path.join(self.yaml_dir, f"{self.scenario}.yaml")
        container = self.client.containers.run(
            image="quay.io/openshift-scale/kraken:latest",
            volumes={
                os.environ["KUBECONFIG"]: {"bind": "/root/.kube/config"},
                config_path: {"bind": "/root/kraken/config/config.yaml"},
                scenario_path: {"bind": "/root/kraken/scenarios/loaded_scenario.yaml"},
            },
            name=name,
            detach=True,
        )

        return container


class BackgroundLoop(threading.Thread):
    def __init__(self, action, vms, period=60):
        super(BackgroundLoop, self).__init__()
        self.vms = vms
        self.action = action
        self.period = period
        self.terminate = False

    @staticmethod
    def _migrate(vm):
        with VirtualMachineInstanceMigration(
            name=vm.name, namespace=vm.namespace, vmi=vm.vmi,
        ) as mig:
            mig.wait_for_status(status=mig.Status.SUCCEEDED, timeout=1500)

    @staticmethod
    def _restart(vm):
        vm.restart(timeout=300, wait=False)

    def run(self):
        LOGGER.info(f"{self.__class__}: Starting {self.action} loop")
        while not self.terminate:
            for vm in self.vms:
                if self.action == ChaosScenario.LoopAction.MIGRATE:
                    self._migrate(vm=vm)

                elif self.action == ChaosScenario.LoopAction.RESTART:
                    self._restart(vm=vm)

            time.sleep(self.period)

        LOGGER.info(f"{self.__class__}: {self.action} loop terminated")

    def stop_loop(self):
        self.terminate = True


class ChaosScenario:
    class LoopAction:
        MIGRATE = "migrate"
        RESTART = "restart"

    def __init__(self, client, scenario, loops):
        self.scenario = scenario
        self.kraken = KrakenScenario(scenario=scenario)
        self.loops = loops
        self.threads = []
        self.oc_api_client = client

    def run_scenario(self):
        LOGGER.info(f"{self.__class__}: Running Kraken scenario: {self.scenario}")
        container = self.kraken.run_scenario()
        for line in container.logs(stdout=True, stderr=True, stream=True):
            LOGGER.info(line.decode().strip())
        result = container.wait()
        container.remove()
        return result["StatusCode"] == 0

    def health_check(self):
        LOGGER.info(f"{self.__class__}: Performing post-scenario cluster health check")
        # make sure all nodes are ready
        for node in Node.get(self.oc_api_client):
            node.wait_for_condition(
                condition=Node.Condition.READY,
                status=Node.Condition.Status.TRUE,
                timeout=60,
            )

        # make sure the hyperconverged is ready
        hco = HyperConverged(
            name="kubevirt-hyperconverged",
            namespace=py_config["hco_namespace"],
            client=self.oc_api_client,
        )

        hco.wait_for_condition(
            condition=HyperConverged.Condition.AVAILABLE,
            status=HyperConverged.Condition.Status.TRUE,
            timeout=60,
        )

    def __enter__(self):
        for loop in self.loops:
            loop.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for loop in self.loops:
            loop.stop_loop()
            loop.join()

        self.health_check()
