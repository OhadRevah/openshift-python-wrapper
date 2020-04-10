from resources.utils import NudgeTimers, nudge_delete

from .resource import Resource


API_GROUP = "project.openshift.io"


class Project(Resource):
    """
    Project object.
    This is openshift's object which represents Namespace
    """

    api_group = API_GROUP

    class Status(Resource.Status):
        ACTIVE = "Active"

    def nudge_delete(self):
        if not hasattr(self, "_timers"):
            self._timers = NudgeTimers()
        nudge_delete(self.name)


class ProjectRequest(Resource):
    """
    RequestProject object.
    Resource which adds Project and grand
    full access to user who originated this request
    """

    api_group = API_GROUP

    def __exit__(self, exception_type, exception_value, traceback):
        if not self.teardown:
            return
        self.clean_up()

    def clean_up(self):
        Project(name=self.name).delete(wait=True)
