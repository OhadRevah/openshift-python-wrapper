import pytest


@pytest.mark.polarion("CNV-7504")
def test_data_import_schedule_default_in_hco_cr(
    data_import_schedule,
):
    # example (the first and second numbers are random):
    # dataImportSchedule: 57 45/12 * * *
    assert data_import_schedule, "No crontab value found"


@pytest.mark.polarion("CNV-8168")
def test_default_hco_cr_image_streams(
    admin_client,
    golden_images_namespace,
    image_stream_names,
    image_streams_from_common_templates_in_ssp_cr,
):
    assert sorted(image_stream_names) == sorted(
        image_streams_from_common_templates_in_ssp_cr
    ), (
        f"ImageStream resources data mismatch: namespace={golden_images_namespace.name} "
        f"cluster image streams={image_stream_names} "
        f"expected image streams names={image_streams_from_common_templates_in_ssp_cr} "
        "missing_image_stream_resources_names_from_ssp_cr="
        f"{set(image_streams_from_common_templates_in_ssp_cr).difference(set(image_stream_names))} "
        "additional_image_stream_names_in_ssp_cr="
        f"{set(image_stream_names).difference(set(image_streams_from_common_templates_in_ssp_cr))}"
    )
