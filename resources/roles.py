from .resource import NamespacedResource, Resource


API_GROUP = "rbac.authorization.k8s.io"


class ClusterRole(Resource):
    """
    ClusrerRole object
    """

    api_group = API_GROUP

    def __init__(self, name, api_groups, permissions_to_resources, verbs):
        super().__init__(name=name)
        self.api_groups = api_groups
        self.permissions_to_resources = permissions_to_resources
        self.verbs = verbs

    def _to_dict(self):
        res = super()._base_body()
        res.update(
            {
                "rules": [
                    {
                        "apiGroups": self.api_groups,
                        "resources": self.permissions_to_resources,
                        "verbs": self.verbs,
                    }
                ]
            }
        )
        return res


class RoleBinding(NamespacedResource):
    """
    RoleBinding object
    """

    api_group = API_GROUP

    def __init__(self, name, namespace, username, role_ref_kind, role_ref_name):
        super().__init__(name=name, namespace=namespace)
        self.username = username
        self.role_ref_kind = role_ref_kind
        self.role_ref_name = role_ref_name

    def _to_dict(self):
        res = super()._to_dict()
        res.update(
            {
                "subjects": [
                    {"kind": "User", "name": self.username, "apiGroup": API_GROUP}
                ],
                "roleRef": {
                    "kind": self.role_ref_kind,
                    "name": self.role_ref_name,
                    "apiGroup": API_GROUP,
                },
            }
        )
        return res
