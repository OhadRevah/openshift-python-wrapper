# -*- coding: utf-8 -*-

import logging

from .resource import NamespacedResource

LOGGER = logging.getLogger(__name__)


class DataVolume(NamespacedResource):
    """
    DataVolume object.
    """

    api_version = 'cdi.kubevirt.io/v1alpha1'
    kind = 'DataVolume'
