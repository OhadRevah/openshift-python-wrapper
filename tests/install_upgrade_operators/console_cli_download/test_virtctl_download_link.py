import pytest


@pytest.mark.polarion("CNV-4481")
def test_ccd_links(virtctl_ccd):
    """
    Check virtctl cli link.
    """
    assert any(
        link["href"] == "https://access.redhat.com/downloads/content/473"
        for link in virtctl_ccd.instance.spec["links"]
    )
