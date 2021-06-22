from http import HTTPStatus

import pytest
from openshift.dynamic.exceptions import ForbiddenError

from utilities.virt import Prometheus


ERRORS = r"unprivileged-user.*" r"cannot get resource.*"


class TestKeyMetricsNegative:
    @pytest.mark.polarion("CNV-6607")
    def test_key_metric_query_negative(
        self,
        unprivileged_client,
    ):
        """
        Tests validating that an unprivileged user can not make prometheus API calls
        """
        assert (
            unprivileged_client
        ), "No ability to create non privileged API client to be used for Prometheus calls"

        with pytest.raises(ForbiddenError, match=ERRORS) as exp:
            Prometheus(client=unprivileged_client)

        assert (
            exp.value.status == HTTPStatus.FORBIDDEN
        ), f"Prometheus query with unprivileged user failed with exception: {exp.value}"
