import logging
import shlex

from utilities.exceptions import CommandExecFailed
from utilities.infra import run_ssh_commands


LOGGER = logging.getLogger(__name__)


def traffic_management_request(vm, **kwargs):
    return run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(
            f"curl -H host:{kwargs['server'].host} http://{kwargs['destination']}/version"
        ),
    )


def assert_traffic_management_request(vm, server, destination):
    output = traffic_management_request(vm=vm, server=server, destination=destination)[
        0
    ].strip()

    assert (
        output == server.version
    ), f"Desired response - {server.version}, actual response - {output}"


def authentication_request(vm, **kwargs):
    return run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"curl http://{kwargs['service']}:8000/ip"),
    )


def assert_authentication_request(vm, service):

    try:
        output = authentication_request(vm=vm, service=service)[0].strip()
        LOGGER.info(f"Deployment response - {output}")
    except CommandExecFailed:
        LOGGER.error("VM couldn't reach deployment")
        raise


def inbound_request(vm, destination_address, destination_port):
    return run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"curl http://{destination_address}:{destination_port}"),
    )
