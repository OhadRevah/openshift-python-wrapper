import logging

import yaml
from ocp_resources.chaos_engine import ChaosEngine

from tests.chaos.constants import (
    CHAOS_ENGINE_FILE,
    CHAOS_ENGINE_NAME,
    LITMUS_NAMESPACE,
    LITMUS_SERVICE_ACCOUNT,
    SCENARIOS_PATH_SOURCE,
)


LOGGER = logging.getLogger(__name__)


class ChaosEngineFile(ChaosEngine):
    def __init__(self, app_info=None, experiments=None):
        """
        Initializes ChaosEngine object, loads the ChaosEngine template file and stores it  as dict in self.body.
        Args:
            app_info (AppInfo): AppInfo object containing information about the chaos target.
            experiments (List[Experiment]): List of Experiment objects.
        """
        self.api_version = f"{self.api_group}/{ChaosEngine.ApiVersion.V1ALPHA1}"
        super().__init__(name=CHAOS_ENGINE_NAME, namespace=LITMUS_NAMESPACE)
        self.app_info = app_info
        self.experiments = experiments

    def to_dict(self):
        self.res = super().to_dict()
        self.res.setdefault("spec", {})
        self.res["spec"].update(
            {
                "annotationCheck": "false",
                "engineState": "active",
                "chaosServiceAccount": LITMUS_SERVICE_ACCOUNT,
                "monitoring": False,
                "jobCleanUpPolicy": "retain",
            }
        )
        if self.app_info:
            self.res["spec"].update(self.app_info.as_dict())
        if self.experiments:
            self.res["spec"]["experiments"] = []
            for experiment in self.experiments:
                self.res["spec"]["experiments"].append(experiment.as_dict())

    def create_yaml(self):
        """
        Creates the ChaosEngine file to be used in the scenarios after updating self.body.
        This file is created anew in every test and it is automatically deleted at the end of each scenario.
        """
        if not self.res:
            self.to_dict()
        chaos_engine_file = f"{SCENARIOS_PATH_SOURCE}{CHAOS_ENGINE_FILE}"
        try:
            with open(chaos_engine_file, "w") as _file:
                yaml.dump(self.res, _file)
            return chaos_engine_file
        except Exception as exp:
            LOGGER.debug(
                f"Failed to create ChaosEngine file: {chaos_engine_file} {exp}"
            )
            raise


class Experiment:
    def __init__(self, name, probes=None, env_components=None):
        """
        Initializes Experiment object.
        Args:
            probes (List[Probe]): List of probes to be used in the experiment.
            env_components (List[EnvComponent]): List of env components to be used in the experiment.
        """
        self.name = name
        self.probes = probes
        self.env_components = env_components

    def as_dict(self):
        dict = {
            "name": self.name,
            "spec": {
                "probe": [],
                "components": {"env": []},
            },
        }
        for probe in self.probes:
            dict["spec"]["probe"].append(probe.as_dict())
        for component in self.env_components:
            dict["spec"]["components"]["env"].append(component.as_dict())
        return dict


class Probe:
    def __init__(
        self,
        name,
        probe_type,
        mode,
        probe_timeout,
        interval,
        retries,
        group=None,
        version=None,
        resource=None,
        namespace=None,
        operation=None,
        label_selector=None,
    ):
        self.name = name
        self.mode = mode
        self.type = probe_type
        self.group = group
        self.version = version
        self.resource = resource
        self.namespace = namespace
        self.label_selector = label_selector
        self.operation = operation
        self.probe_timeout = probe_timeout
        self.interval = interval
        self.retries = retries

    def as_dict(self):
        return {
            "name": self.name,
            "type": self.type,
            f"{self.type}/inputs": {
                "group": self.group,
                "version": self.version,
                "resource": self.resource,
                "namespace": self.namespace,
                "labelSelector": self.label_selector,
                "operation": self.operation,
            },
            "mode": self.mode,
            "runProperties": {
                "probeTimeout": self.probe_timeout,
                "interval": self.interval,
                "retry": self.retries,
            },
        }


class EnvComponent:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def as_dict(self):
        return {"name": self.name, "value": self.value}


class AppInfo:
    def __init__(self, namespace, label, kind):
        self.namespace = namespace
        self.label = label
        self.kind = kind

    def as_dict(self):
        return {
            "appinfo": {
                "appns": self.namespace,
                "applabel": self.label,
                "appkind": self.kind,
            }
        }
