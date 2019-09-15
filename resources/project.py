from .resource import Resource


API_GROUP = "project.openshift.io"


class Project(Resource):
    """
    Project object.
    This is openshift's object which represents Namespace
    """

    api_group = API_GROUP

    class Status:
        ACTIVE = "Active"


class ProjectRequest(Resource):
    """
    RequestProject object.
    Resource which adds Project and grand
    full access to user who originated this request
    """

    api_group = API_GROUP

    def __exit__(self, exception_type, exception_value, traceback):
        Project(name=self.name).delete(wait=True)
