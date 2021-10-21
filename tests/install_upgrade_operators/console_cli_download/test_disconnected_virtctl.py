import os.path

import pytest


pytestmark = pytest.mark.sno


class TestDisconnectedVirtctlDownload:
    @pytest.mark.parametrize(
        "downloaded_and_extracted_virtctl_binary_for_os",
        [
            pytest.param(
                "win",
                marks=(pytest.mark.polarion("CNV-6914"),),
                id="test_download_virtcli_binary_win",
            ),
            pytest.param(
                "mac",
                marks=(pytest.mark.polarion("CNV-6954"),),
                id="test_download_virtcli_binary_mac",
            ),
        ],
        indirect=True,
    )
    def test_download_virtcli_binary(
        self,
        downloaded_and_extracted_virtctl_binary_for_os,
    ):
        assert os.path.exists(downloaded_and_extracted_virtctl_binary_for_os)


class TestDisconnectedVirtctlDownloadAndExecute:
    @pytest.mark.parametrize(
        "downloaded_and_extracted_virtctl_binary_for_os",
        [
            pytest.param(
                "linux",
                marks=(pytest.mark.polarion("CNV-6913"),),
                id="test_download_virtcli_binary_linux",
            ),
        ],
        indirect=True,
    )
    def test_download_and_execute_virtcli_binary_linux(
        self, virtctl_client_and_server_versions
    ):
        assert len(virtctl_client_and_server_versions) == 2, (
            "regex did not produced the expected number of matches: "
            "virtctl_client_and_server_versions={virtctl_client_and_server_versions}"
        )
        assert len(set(virtctl_client_and_server_versions)) == 1, (
            "Compare error: virtctl client and server versions are not identical: "
            f"client_and_server_versions={virtctl_client_and_server_versions}"
        )


class TestDisconnectedVirtctlAllLinksInternal:
    @pytest.mark.polarion("CNV-6915")
    def test_all_links_internal(self, all_virtctl_urls, non_internal_fqdns):
        assert not non_internal_fqdns, (
            "Found virtctl URLs that do not point to the cluster internally: "
            f"violating_fqdns={non_internal_fqdns} all_virtctl_urls={all_virtctl_urls}"
        )
