import logging
from datetime import datetime

import podman

from tests.chaos.constants import (
    KRAKEN_IMAGE,
    MOUNTS,
    NETWORK_MODE_HOST,
    PLATFORM_LINUX,
)
from utilities.infra import run_command, write_to_extras_file


LOGGER = logging.getLogger(__name__)


class KrakenContainer:
    def __init__(self, name=f"krkn-{datetime.now().strftime('%d-%m-%Y-%H-%M-%S')}"):
        self.name = name
        self.client = podman.PodmanClient(base_url=self._get_podman_uri())
        self.image = self.client.images.pull(
            repository=KRAKEN_IMAGE, platform=PLATFORM_LINUX
        )
        self.container = None

    def run(self):
        """Runs a container with the kraken image and stores it in self.container."""
        self.container = self.client.containers.run(
            name=self.name,
            image=self.image,
            mounts=MOUNTS,
            network_mode=NETWORK_MODE_HOST,
            detach=True,
            privileged=True,
            auto_remove=True,
            remove=True,
        )

    def wait(self):
        """
        Waits for the container to exit.
        Returns:
            bool: True if the container runs successfully.
        """
        result = self.container.wait()

        if result != 0:
            self._get_logs()

        return result == 0

    def _get_logs(self):
        log = "".join(
            [item.decode("utf-8") for item in list(self.container.logs(stderr=True))]
        )

        for line in log.splitlines()[-20:]:
            LOGGER.info(line)

        write_to_extras_file(
            extras_file_name="container_logs.txt", content=log, extra_dir_name="kraken"
        )

    def _get_podman_uri(self):
        """
        Gets podman service socket uri through systemctl.
        """
        rc, out, err = run_command(
            command=["systemctl", "--user", "list-sockets", "podman.socket"],
            verify_stderr=False,
        )
        lines = out.splitlines()
        socket = lines[1].split(" ")[0]
        return f"unix://{socket}"
