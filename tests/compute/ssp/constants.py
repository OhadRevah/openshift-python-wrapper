# TODO: Add evmcs for fedora and Windows hyperV features, once merged
# https://bugzilla.redhat.com/show_bug.cgi?id=1952551

HYPERV_FEATURES_LABELS_DOM_XML = [
    "relaxed",
    "vapic",
    "spinlocks",
    "vpindex",
    "synic",
    "stimer",  # synictimer in VM yaml
    "frequencies",
    "ipi",
    "reenlightenment",
    "reset",
    "runtime",
    "tlbflush",
]

HYPERV_FEATURES_LABELS_VM_YAML = HYPERV_FEATURES_LABELS_DOM_XML.copy()
HYPERV_FEATURES_LABELS_VM_YAML[
    HYPERV_FEATURES_LABELS_VM_YAML.index("stimer")
] = "synictimer"
