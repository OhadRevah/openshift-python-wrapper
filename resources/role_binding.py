# -*- coding: utf-8 -*-

from .resource import NamespacedResource


API_GROUP = "rbac.authorization.k8s.io"


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
