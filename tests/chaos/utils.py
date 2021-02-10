import json
import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime

import docker
import requests
import yaml
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


class ScenarioError(Exception):
    def __init__(self, scenario, reason):
        self.scenario = scenario
        self.reason = reason

    def __str__(self):
        return f"Scenario {self.scenario} failed with {self.reason}"


class LitmusScenario:
    def __init__(self, scenario, kind):
        self.scenario = scenario
        self.kind = kind
        self.litmus_dir = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "litmus/"
        )
        self.config = self._load_config()

    def run_scenario(self):
        scenarios = self.config["repo"]["scenariodir"]
        scenario_dir = os.path.join(scenarios, self.kind, self.scenario)

        self._fetch_scenario(scenario_dir=scenario_dir)
        init_script = os.path.join(scenario_dir, "init_engine.sh")
        self._run_script(script=init_script)

    def _fetch_file(self, filename, directory=""):
        repo = self.config["repo"]
        if not os.path.isfile(os.path.join(self.litmus_dir, directory, filename)):
            url = f"https://{repo['url']}/{repo['org']}/{repo['project']}/-/raw/{repo['branch']}/{directory}/{filename}"
            resp = requests.get(url, verify=False)
            if resp.status_code != 200:
                raise requests.HTTPError("Failed to fetch file from remote repository")

            if directory != "":
                os.makedirs(os.path.join(self.litmus_dir, directory), exist_ok=True)

            open(os.path.join(self.litmus_dir, directory, filename), "wb").write(
                resp.content
            )

    def _fetch_file_list(self, scenario, directory):
        repo = self.config["repo"]
        project = f"{repo['org']}%2F{repo['project']}"

        url = f"https://{repo['url']}/api/v4/projects/{project}/repository/tree?path={directory}{self.kind}/{scenario}"
        resp = requests.get(url, verify=False)
        if resp.status_code != 200:
            raise requests.HTTPError("Not able to list directories")

        return [
            filename["name"] for filename in json.loads(resp.content.decode("utf-8"))
        ]

    def _fetch_scenario(self, scenario_dir):
        filenames = self._fetch_file_list(
            scenario=self.scenario, directory=self.config["repo"]["scenariodir"]
        )
        for filename in filenames:
            self._fetch_file(filename=filename, directory=scenario_dir)

        self._make_executable(filename="init_engine.sh", directory=scenario_dir)
        self._make_executable(filename="cleanup.sh", directory=scenario_dir)

    def _make_executable(self, filename, directory=""):
        os.chmod(os.path.join(self.litmus_dir, directory, filename), 0o775)

    def _load_config(self):
        with open(os.path.join(self.litmus_dir, "config.yaml"), "r") as data:
            return yaml.safe_load(data)

    def _deploy(self):
        script_dir = self.config["repo"]["deploydir"]
        self._fetch_file(filename="compute-tests-to-run.sh", directory=script_dir)
        self._fetch_file(filename="deploy-litmus.sh", directory=script_dir)
        self._make_executable(filename="deploy-litmus.sh", directory=script_dir)
        self._fetch_file(filename="common.sh", directory=script_dir)
        self._fetch_file(filename="variables.sh", directory=script_dir)

        deploy_script = os.path.join(self.litmus_dir, script_dir, "deploy-litmus.sh")
        self._run_script(script=deploy_script)

    def _run_script(self, script):
        returncode = subprocess.Popen(
            script,
            env={
                "KUBECONFIG": os.getenv("KUBECONFIG"),
                "HOST_IP": os.environ.get("HOST_IP", self.config["env"]["host"]),
                "GROUP": self.kind,
                "NODE_SSH_KEY": os.environ.get(
                    "NODE_SSH_KEY", self.config["env"]["key"]
                ),
            },
            cwd=self.litmus_dir,
        ).wait()

        if returncode != 0:
            raise ScenarioError(
                scenario=self.scenario, reason="Failed to deploy litmus."
            )

    def _file_cleanup(self, scenario_dir):
        keep = os.getenv("CNV_TESTS_CHAOS_KEEP_DATA", 0)
        if keep != 0:
            return

        try:
            shutil.rmtree(os.path.join(self.litmus_dir, scenario_dir))
        except OSError:
            LOGGER.warning(
                f"{self.__class__}: Failed to remove scenario: {self.scenario}"
            )

    def __enter__(self):
        self._deploy()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        scenarios = self.config["repo"]["scenariodir"]
        scenario_dir = os.path.join(scenarios, self.kind, self.scenario)

        try:
            script = os.path.join(scenario_dir, "cleanup.sh")
            self._run_script(script=script)
            self._file_cleanup(scenario_dir=scenarios)
        except ScenarioError:
            LOGGER.warning(f"{self.__class__}: Failed to cleanup: {self.scenario}")


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
            name=vm.name,
            namespace=vm.namespace,
            vmi=vm.vmi,
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
