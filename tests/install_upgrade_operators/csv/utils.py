import logging

from openshift.dynamic.exceptions import NotFoundError

from utilities.infra import get_kubevirt_package_manifest


LOGGER = logging.getLogger(__name__)


def get_package_manifest_images(admin_client, channel_name="stable"):
    package = get_kubevirt_package_manifest(admin_client=admin_client)
    for channel in package.status.channels:
        if channel.name == channel_name:
            LOGGER.info(
                "For kubevirt package manifest {channel_name} channel was found."
            )
            return channel.currentCSVDesc["relatedImages"]
    raise NotFoundError(
        f"For kubevirt package manifest, could not find {channel_name} channel"
    )
