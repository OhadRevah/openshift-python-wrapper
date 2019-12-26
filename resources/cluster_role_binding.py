# -*- coding: utf-8 -*-

from .resource import NamespacedResource


class ClusterRoleBinding(NamespacedResource):
    """
    ClusterRoleBinding object.
    """

    api_group = "rbac.authorization.k8s.io"
