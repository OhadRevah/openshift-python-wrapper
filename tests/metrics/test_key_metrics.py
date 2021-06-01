import pytest

from tests.metrics import utils


@pytest.mark.usefixtures("vm_list", "prometheus")
class TestKeyMetrics:
    @pytest.mark.parametrize(
        "query",
        [
            pytest.param(
                "kubevirt_vmi_network_receive_bytes_total",
                marks=pytest.mark.polarion("CNV-6174"),
                id="kubevirt_vmi_network_receive_bytes_total",
            ),
            pytest.param(
                "kubevirt_vmi_network_transmit_bytes_total",
                marks=pytest.mark.polarion("CNV-6175"),
                id="kubevirt_vmi_network_transmit_bytes_total",
            ),
            pytest.param(
                "kubevirt_vmi_storage_iops_write_total",
                marks=pytest.mark.polarion("CNV-6176"),
                id="kubevirt_vmi_storage_iops_write_total",
            ),
            pytest.param(
                "kubevirt_vmi_storage_iops_read_total",
                marks=pytest.mark.polarion("CNV-6177"),
                id="kubevirt_vmi_storage_iops_read_total",
            ),
            pytest.param(
                "kubevirt_vmi_storage_write_traffic_bytes_total",
                marks=pytest.mark.polarion("CNV-6178"),
                id="kubevirt_vmi_storage_write_traffic_bytes_total",
            ),
            pytest.param(
                "kubevirt_vmi_storage_read_traffic_bytes_total",
                marks=pytest.mark.polarion("CNV-6179"),
                id="kubevirt_vmi_storage_read_traffic_bytes_total",
            ),
            pytest.param(
                "kubevirt_vmi_vcpu_wait_seconds",
                marks=pytest.mark.polarion("CNV-6180"),
                id="kubevirt_vmi_vcpu_wait_seconds",
            ),
            pytest.param(
                "kubevirt_vmi_memory_swap_in_traffic_bytes_total",
                marks=pytest.mark.polarion("CNV-6181"),
                id="kubevirt_vmi_memory_swap_in_traffic_bytes_total",
            ),
            pytest.param(
                "kubevirt_vmi_memory_swap_out_traffic_bytes_total",
                marks=pytest.mark.polarion("CNV-6182"),
                id="kubevirt_vmi_memory_swap_out_traffic_bytes_total",
            ),
        ],
    )
    def test_key_metric_passive(self, prometheus, first_metric_vm, query):
        """
        Tests validating ability to perform various prometheus api queries on various metrics against a given vm.
        This test also validates ability to pull metric information from a given vm's virt-handler pod and validates
        appropriate value exists for that metrics.

        """
        vm = first_metric_vm
        vm_name_from_metric = utils.get_vm_names_from_metric(
            prometheus=prometheus, query=query
        )
        assert vm.name in vm_name_from_metric, (
            f"Expected vm name: {vm.name} not found in prometheus api query "
            f"result: {vm_name_from_metric}"
        )
        utils.assert_vm_metric_virt_handler_pod(query=query, vm=vm)
