import logging
import subprocess
import time

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
        # remember the time of the first delete attempt
        if not hasattr(self, "_nudge_start_time"):
            self._nudge_start_time = time.time()
        # delay active nudging in hope regular delete procedure will succeed
        current_time = time.time()
        if current_time - _DELETE_NUDGE_DELAY < self._nudge_start_time:
            return
        # don't nudge more often than once in 5 seconds
        if getattr(self, "_last_nudge", 0) + _DELETE_NUDGE_INTERVAL > current_time:
            return
        LOGGER.info(f"Nudging namespace {self.name} while waiting for it to delete")
        try:
            # kube client is deficient so we have to use curl to kill stuck
            # finalizers
            subprocess.check_output(["./scripts/clean-namespace.sh", self.name])
            self._last_nudge = time.time()
        except subprocess.CalledProcessError as e:
            # deliberately ignore all errors since an intermittent nudge
            # failure is not the end of the world
            LOGGER.info(f"Error happened while nudging namespace {self.name}: {e}")
