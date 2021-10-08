import shlex

from utilities.infra import run_ssh_commands


def traffic_management_request(vm, server, destination):
    return run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(
            f"curl -H host:{server.host} http://{destination}/version"
        ),
    )


def assert_traffic_management_request(vm, server, destination):
    output = traffic_management_request(vm=vm, server=server, destination=destination)[
        0
    ].strip()

    assert (
        output == server.version
    ), f"Desired response - {server.version}, actual response - {output}"
