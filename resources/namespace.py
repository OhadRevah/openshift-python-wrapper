import logging

from resources.utils import nudge_delete
from .resource import Resource

LOGGER = logging.getLogger(__name__)

_DELETE_NUDGE_DELAY = 30
_DELETE_NUDGE_INTERVAL = 5


class Namespace(Resource):
    """
    Namespace object, inherited from Resource.
    """

    api_version = "v1"

    class Status:
        ACTIVE = "Active"

    # TODO: remove the nudge when the underlying issue with namespaces stuck in
    # Terminating state is fixed.
    # Upstream bug: https://github.com/kubernetes/kubernetes/issues/60807
    def nudge_delete(self):
        nudge_delete(self.name)
