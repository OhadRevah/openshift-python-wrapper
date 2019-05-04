import json

import kubernetes

from .node import Node
from .resource import NamespacedResource


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
    api_version = 'v1'
    kind = 'Pod'

    class Status:
        RUNNING = 'Running'

    def __init__(self, name=None, namespace=None):
        super(Pod, self).__init__(name=name, namespace=namespace)
        self.kube_api = kubernetes.client.CoreV1Api(api_client=self.client.client)

    def containers(self):
        """
        Get Pod containers

        Returns:
            list: List of Pod containers
        """
        return self.get().spec.containers

    def exec(self, command, timeout=60, container=None):
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
            func=self.kube_api.connect_get_namespaced_pod_exec,
            name=self.name,
            namespace=self.namespace,
            command=command,
            container=container or self.containers()[0].name,
            stderr=True, stdin=False,
            stdout=True, tty=False,
            _preload_content=False
        )
        resp.run_forever(timeout=timeout)
        stdout = resp.read_stdout()
        stderr = resp.read_stderr()
        error_channel = json.loads(resp.read_channel(kubernetes.stream.ws_client.ERROR_CHANNEL))
        if error_channel['status'] == 'Success':
            returncode = 0
        else:
            returncode = [
                int(cause['message']) for cause in error_channel['details']['causes']
                if cause['reason'] == 'ExitCode'][0]
        if returncode:
            raise ExecOnPodError(command=command, rc=returncode, out=stdout, err=stderr)
        return stdout

    def node(self):
        """
        Get the node name where the Pod is running

        Returns:
            Node: Node
        """
        return Node(name=self.get().spec.nodeName)
