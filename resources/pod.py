import json

import kubernetes

from .node import Node
from .resource import NamespacedResource
from . import utils


class ExecOnPodError(Exception):
    def __init__(self, command, rc, out, err):
        self.cmd = command
        self.rc = rc
        self.out = out
        self.err = err

    def __str__(self):
        return (
            f"Command execution failure: "
            f"{self.cmd}, "
            f"RC: {self.rc}, "
            f"OUT: {self.out}, "
            f"ERR: {self.err}"
        )


class Pod(NamespacedResource):
    """
    Pod object, inherited from Resource.
    """

    api_version = "v1"

    class Status:
        RUNNING = "Running"

    def __init__(self, name, namespace, client=None):
        super().__init__(name=name, namespace=namespace, client=client)
        self._kube_api = kubernetes.client.CoreV1Api(api_client=self.client.client)

    @property
    def containers(self):
        """
        Get Pod containers

        Returns:
            list: List of Pod containers
        """
        return self.instance.spec.containers

    def execute(self, command, timeout=60, container=None):
        """
        Run command on Pod

        Args:
            command (list): Command to run.
            timeout (int): Time to wait for the command.
            container (str): Container name where to exec the command.

        Returns:
            str: Command output.

        Raises:
            ExecOnPodError: If the command failed.
        """
        resp = kubernetes.stream.stream(
            func=self._kube_api.connect_get_namespaced_pod_exec,
            name=self.name,
            namespace=self.namespace,
            command=command,
            container=container or self.containers[0].name,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _preload_content=False,
        )
        timeout_watch = utils.TimeoutWatch(timeout)
        resp.run_forever(timeout=timeout_watch.remaining_time())
        stdout = resp.read_stdout(timeout=timeout_watch.remaining_time())
        stderr = resp.read_stderr(timeout=timeout_watch.remaining_time())
        error_channel = json.loads(
            resp.read_channel(kubernetes.stream.ws_client.ERROR_CHANNEL)
        )
        if error_channel["status"] == "Success":
            returncode = 0
        else:
            returncode = [
                int(cause["message"])
                for cause in error_channel["details"]["causes"]
                if cause["reason"] == "ExitCode"
            ][0]
        if returncode:
            raise ExecOnPodError(command=command, rc=returncode, out=stdout, err=stderr)
        return stdout

    def log(self, **kwargs):
        """
        Get Pod logs

        Returns:
            str: Pod logs.
        """
        return self._kube_api.read_namespaced_pod_log(
            self.name, self.namespace, **kwargs
        )

    @property
    def node(self):
        """
        Get the node name where the Pod is running

        Returns:
            Node: Node
        """
        return Node(name=self.instance.spec.nodeName)
