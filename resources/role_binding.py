# -*- coding: utf-8 -*-

from .resource import NamespacedResource


API_GROUP = "rbac.authorization.k8s.io"


class RoleBinding(NamespacedResource):
    """
    RoleBinding object
    """

    api_group = API_GROUP

    def __init__(
        self, name, namespace, username=None, role_ref_kind=None, role_ref_name=None
    ):
        super().__init__(name=name, namespace=namespace)
        self.username = username
        self.role_ref_kind = role_ref_kind
        self.role_ref_name = role_ref_name

    def _to_dict(self):
        res = super()._to_dict()

        subjects = {}
        subjects["kind"] = ("User",)
        subjects["apiGroup"] = API_GROUP
        if self.username:
            subjects["name"] = self.username
        res["subjects"] = [subjects]

        roleref = {}
        roleref["apiGroup"] = API_GROUP
        if self.role_ref_kind:
            roleref["role_ref_kind"] = self.role_ref_kind
        if self.role_ref_name:
            roleref["role_ref_name"] = self.role_ref_name
        res["roleRef"] = [roleref]

        return res
