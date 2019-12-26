# -*- coding: utf-8 -*-

from .resource import Resource


class ClusterRole(Resource):
    """
    ClusterRole object
    """

    api_group = "rbac.authorization.k8s.io"

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
