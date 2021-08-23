import pytest


@pytest.mark.polarion("CNV-7169")
def test_only_stable_channel_in_subscription(stable_channel_package_manifest):
    """
    Check only stable channel is available on the CNV Subscription.
    """

    assert stable_channel_package_manifest == ["stable"], (
        f"Expected only 'stable' channels."
        f"Actual available channels {stable_channel_package_manifest}"
    )
