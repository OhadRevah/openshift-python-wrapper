# NAMESPACES
TEST_NS = "kubevirt-test-default"
TEST_NS_ALTERNATIVE = "kubevirt-test-alternative"
KUBEVIRT_NS = "kubevirt"
NETWORK_NS = "network-tests-namespace"
VIRT_NS = "cnv-virt-ns"


# VM distro
FEDORA_VM = "fedora"
CIRROS_VM = "cirros"

# VMS TEMPLATES
VM_YAML_TEMPLATE = "tests/manifests/vm-template-fedora.yaml"

# UTILS
IP_LINK_SHOW_VETH_CMD = ["bash", "-c", "ip -o link show type veth | wc -l"]
