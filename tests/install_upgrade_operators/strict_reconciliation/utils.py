import importlib
import logging

from dictdiffer import diff
from ocp_resources.resource import ResourceEditor
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_CA_KEY,
    HCO_CR_CERT_CONFIG_DURATION_KEY,
    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY,
    HCO_CR_CERT_CONFIG_SERVER_KEY,
)
from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CERTC_DEFAULT_12H,
    CERTC_DEFAULT_24H,
    CERTC_DEFAULT_48H,
    KV_CR_FEATUREGATES_HCO_CR_DEFAULTS,
)
from tests.install_upgrade_operators.utils import (
    get_function_name,
    get_network_addon_config,
    wait_for_cr_labels_change,
)
from utilities.constants import TIMEOUT_3MIN
from utilities.hco import get_hco_spec
from utilities.infra import get_hyperconverged_resource
from utilities.storage import get_hyperconverged_cdi
from utilities.virt import get_hyperconverged_kubevirt


LOGGER = logging.getLogger(__name__)


def verify_spec(expected_spec, get_spec_func):
    samplers = TimeoutSampler(
        wait_timeout=60,
        sleep=5,
        exceptions_dict={AssertionError: []},
        func=lambda: list(diff(expected_spec, get_spec_func())),
    )
    diff_result = None
    try:
        for diff_result in samplers:
            if not diff_result:
                return True

    except TimeoutExpiredError:
        LOGGER.error(
            f"{get_function_name(function_name=get_spec_func)}: Timed out waiting for CR with expected spec."
            f" spec: '{expected_spec}' diff:'{diff_result}'"
        )
        raise


def verify_specs(
    admin_client,
    hco_namespace,
    hco_spec,
    kubevirt_hyperconverged_spec_scope_function,
    cdi_spec,
    cnao_spec,
):
    verify_spec(
        expected_spec=hco_spec,
        get_spec_func=lambda: get_hco_spec(
            admin_client=admin_client, hco_namespace=hco_namespace
        ),
    )
    verify_spec(
        expected_spec=kubevirt_hyperconverged_spec_scope_function,
        get_spec_func=lambda: get_hyperconverged_kubevirt(
            admin_client=admin_client, hco_namespace=hco_namespace
        )
        .instance.to_dict()
        .get("spec"),
    )
    verify_spec(
        expected_spec=cdi_spec,
        get_spec_func=lambda: get_hyperconverged_cdi(admin_client=admin_client)
        .instance.to_dict()
        .get("spec"),
    )
    verify_spec(
        expected_spec=cnao_spec,
        get_spec_func=lambda: get_network_addon_config(admin_client=admin_client)
        .instance.to_dict()
        .get("spec"),
    )
    # when none of the functions above raise TimeoutExpiredError
    return True


def validate_featuregates_not_in_kv_cr(
    admin_client, hco_namespace, feature_gates_under_test
):
    kv_fgs = get_hyperconverged_kubevirt(
        admin_client=admin_client, hco_namespace=hco_namespace
    ).instance.to_dict()["spec"]["configuration"]["developerConfiguration"][
        "featureGates"
    ]
    return all(
        [
            (fg in kv_fgs) == KV_CR_FEATUREGATES_HCO_CR_DEFAULTS.get(fg, False)
            for fg in feature_gates_under_test
        ]
    )


def validate_featuregates_not_in_cdi_cr(
    admin_client, hco_namespace, feature_gates_under_test
):
    """
    Validates that all expected featuregates are present in cdi CR

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace (Namespace): Namespace object
        feature_gates_under_test (list): list of featuregates to compare against current list of featuregates
    returns:
        bool: returns True or False
    """
    cdi = get_hyperconverged_cdi(admin_client=admin_client).instance.to_dict()

    cdi_fgs = cdi["spec"]["config"]["featureGates"]
    return all(fg not in cdi_fgs for fg in feature_gates_under_test)


def compare_expected_with_cr(expected, actual):
    # filtering out the "add" verb - it contains additional keys that do not exist in the expected dict, and are
    # other fields in the spec that are not tested and irrelevant to this test
    return list(
        filter(
            lambda diff_result_item: diff_result_item[0] != "add",
            list(diff(expected, actual)),
        )
    )


def expected_certconfig_stanza():
    return {
        HCO_CR_CERT_CONFIG_CA_KEY: {
            HCO_CR_CERT_CONFIG_DURATION_KEY: CERTC_DEFAULT_48H,
            HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: CERTC_DEFAULT_24H,
        },
        HCO_CR_CERT_CONFIG_SERVER_KEY: {
            HCO_CR_CERT_CONFIG_DURATION_KEY: CERTC_DEFAULT_24H,
            HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: CERTC_DEFAULT_12H,
        },
    }


def wait_for_fg_update(admin_client, hco_namespace, expected_fg, validate_func):
    """
    Waits for featuregate updates to get propagated

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace (Namespace): Namespace object
        expected_fg (list): list of featuregates to compare against current list of featuregates
        validate_func (function): validate function to be used for comparison
    """
    samples = TimeoutSampler(
        wait_timeout=30,
        sleep=1,
        func=validate_func,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        feature_gates_under_test=expected_fg,
    )
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Timeout validating featureGates field values using "
            f"{get_function_name(function_name=validate_func)}: comparing with fg: {expected_fg}"
        )
        raise


def get_ocp_resource_module_name(related_object_kind, list_submodules):
    """
    From a list of ocp_resources submodule, based on kubernetes 'kind' name pick the right module name

    Args:
        related_object_kind (str): Kubernetes kind name of a resource
        list_submodules (list): list of ocp_resources submodule names

    Returns:
        str: Name of the ocp_resources submodule

    Raises:
        ModuleNotFoundError: if a module associated with related object kind is not found
    """
    for module_name in list_submodules:
        expected_module_name = module_name.replace("_", "")
        if related_object_kind.lower() == expected_module_name:
            return module_name
    raise ModuleNotFoundError(
        f"{related_object_kind} module not found in ocp_resources"
    )


def get_resource(related_obj, admin_client, module_name):
    """
    Gets CR based on associated HCO.status.relatedObject entry and ocp_reources module name

    Args:
        related_obj (dict): Associated HCO.status.relatedObject dict
        admin_client (DynamicClient): Dynamic client object
        module_name (str): Associated ocp_reources module name to be used

    Returns:
        Resource: Associated cr object

    Raises:
        AssertionError: if a related object kind is not in module name
    """
    kwargs = {"client": admin_client, "name": related_obj["name"]}
    if related_obj["namespace"]:
        kwargs["namespace"] = related_obj["namespace"]

    module = importlib.import_module(f"ocp_resources.{module_name}")
    cls_related_obj = getattr(module, related_obj["kind"], None)
    assert cls_related_obj, f"class {related_obj['kind']} is not in {module_name}"
    LOGGER.info(f"reading class {related_obj['kind']} from module {module_name}")
    return cls_related_obj(**kwargs)


def update_resource_label(component):
    """
    Adds a label to a CR and waits for an expected value to be updated in the CR.
    Note: This does not need to be undone, since the expected behavior is the cr would be reconciled.

    Args:
        component (Resource): Resource object
    """
    expected_labels_value = component.instance.metadata.labels
    resource_update = ResourceEditor(
        patches={component: {"metadata": {"labels": {"temp_label": "test"}}}}
    )
    resource_update.update(backup_resources=False)
    wait_for_cr_labels_change(expected_value=expected_labels_value, component=component)


def get_hco_related_object_version(client, hco_namespace, resource_name, resource_kind):
    """
    Gets related object version from hco.status.relatedObject

    Args:
        client (DynamicClient): Dynamic client object
        hco_namespace (Namespace): Namespace object
        resource_name (str): Name of the resource
        resource_kind (str): resource kind

    Returns:
        str: current resourceVersion from hco.status.relatedObject
    """
    related_objects = get_hyperconverged_resource(
        client=client, hco_ns_name=hco_namespace.name
    ).instance.status.relatedObjects
    for related_obj in related_objects:
        if (
            related_obj["kind"] == resource_kind
            and related_obj["name"] == resource_name
        ):
            return related_obj["resourceVersion"]


def wait_for_hco_related_object_version_change(
    admin_client, hco_namespace, component, resource_kind
):
    """
    Waits for hco.status.relatedObject to get updated with expected resourceVersion value

    Args:
        admin_client (DynamicClient): Dynamic client object
        hco_namespace (Namespace): Namespace object
        component (Resource): Resource object
        resource_kind (str): resource kind

    Returns:
        str: empty, in case a match found, else, error string
    """
    resource_name = component.name
    expected_version = component.instance.metadata.resourceVersion
    LOGGER.info(
        f"waiting for {resource_name}/{resource_kind} to reach {expected_version}"
    )
    samplers = TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=5,
        func=get_hco_related_object_version,
        client=admin_client,
        hco_namespace=hco_namespace,
        resource_kind=resource_kind,
        resource_name=resource_name,
    )
    resource_version = None
    error = ""
    try:
        for resource_version in samplers:
            if resource_version == expected_version:
                LOGGER.info(
                    f"For {resource_name}, current resource version: {resource_version} matches with expected"
                    f" value in hco.status.relatedObjects."
                )
                return error

    except TimeoutExpiredError:
        error = (
            f"Component: {resource_name}/{resource_kind} hco.status.relatedObjects was not updated with correct "
            f"resource version: {expected_version}. Actual value: {resource_version}"
        )
        LOGGER.error(error)
        return error


def validate_related_objects(
    related_objects, ocp_resources_submodule_list, admin_client, hco_namespace
):
    """
    Validates all HCO.status.relatedObjects to ensure they get reconciled, appropriate resourceVersion gets reported

    Args:
        related_objects (list): list of dictionary of related objects
        ocp_resources_submodule_list (list): list of ocp_resources submodules
        admin_client (DynamicClient): Dynamic client object
        hco_namespace (Namespace): Namespace object

    Raises:
        AssertionError: if related objects are not reconciled, if resourceVersion is not updated for HCO
    """
    error_reconciliation = {}
    error_resource_version = {}

    for related_obj in related_objects:

        pre_update_resource_version = related_obj["resourceVersion"]
        component = get_resource_from_module_name(
            related_obj=related_obj,
            ocp_resources_submodule_list=ocp_resources_submodule_list,
            admin_client=admin_client,
        )
        pre_update_label = component.instance.metadata.labels
        update_resource_label(
            component=component,
        )

        LOGGER.info(
            f"Checking: {related_obj['kind']}: {related_obj['name']} for reconciliation"
        )
        error_reconciliation[component.name] = validate_resource_reconciliation(
            pre_update_resource_version=pre_update_resource_version,
            component=component,
            pre_update_label=pre_update_label,
        )

        error_resource_version_value = wait_for_hco_related_object_version_change(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            component=component,
            resource_kind=related_obj["kind"],
        )
        if error_resource_version_value:
            error_resource_version[component.name] = error_resource_version_value

    assert not any(error_reconciliation.values()), (
        f"Reconciliation failed for the following related "
        f"object: {error_reconciliation}"
    )
    assert not any(error_resource_version.values()), (
        f"Resource version update on hco.status.relatedObjects did not "
        f"take place for these components: {error_resource_version}"
    )


def get_resource_from_module_name(
    related_obj, ocp_resources_submodule_list, admin_client
):
    """
    Gets resource object based on module name

    Args:
        related_obj (dict): Related object Dictionary
        ocp_resources_submodule_list (list): list of submudule names associated with ocp_resources package
        admin_client (DynamicClient): Dynamic client object

    Returns:
        Resource: Associated cr object
    """
    module_name = get_ocp_resource_module_name(
        related_object_kind=related_obj["kind"],
        list_submodules=ocp_resources_submodule_list,
    )
    return get_resource(
        admin_client=admin_client,
        related_obj=related_obj,
        module_name=module_name,
    )


def validate_resource_reconciliation(
    component, pre_update_resource_version, pre_update_label
):
    """
    Validates a resource is getting reconciled post patch command

    Args:
        component (Resource): Resource object to be checked
        pre_update_resource_version (str): string indicating pre patch resource version
        pre_update_label (dict): Indicates metadata.labels associated with the resource - pre patch

    Returns:
        str: Errors indicating the failure in reconciliation.
    """
    errors = []
    post_update_resource_version = component.instance.metadata.resourceVersion
    post_update_label = component.instance.metadata.labels
    errors.append(
        compare_resource_version(
            pre_update_resource_version=pre_update_resource_version,
            post_update_resource_version=post_update_resource_version,
        )
    )
    errors.append(
        compare_resource_labels(
            pre_update_label=pre_update_label, post_update_label=post_update_label
        )
    )

    return "\n".join(filter(None, errors))


def compare_resource_version(pre_update_resource_version, post_update_resource_version):
    """
    Compare two resource versions and if they are same return an error message

    Args:
        pre_update_resource_version (str): pre update reource version string
        post_update_resource_version (str): post update resource version string

    Returns:
        str: error message string if pre update and post update resource version matches, empty string otherwise
    """
    if pre_update_resource_version == post_update_resource_version:
        return f"Pre update resource version is same as current resource version: {pre_update_resource_version}"
    return ""


def compare_resource_labels(pre_update_label, post_update_label):
    """
    Compare pre update and post update metadata.labels for the same resource and if they are not same return an error
    message

    Args:
        pre_update_label (str): pre update reource version string
        post_update_label (str): post update resource version string

    Returns:
        str: error message string, if pre update and post update resource label does not match, empty string otherwise
    """
    if pre_update_label != post_update_label:
        return f"Pre update labels: {pre_update_label} does not match with post update labels: {post_update_label}"
    return ""


def assert_expected_hardcoded_feature_gates(actual, expected, hco_spec):
    assert sorted(actual) == sorted(expected), (
        "actual featureGates list in KubeVirt CR is not as expected: "
        f"expected={expected} actual={actual} hco_spec: {hco_spec}"
    )


def wait_for_resource_version_change(resource, starting_resource_version):
    LOGGER.info(
        f"For {resource.name} waiting for resourceVersion to change from {starting_resource_version}"
    )
    samplers = TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=5,
        func=lambda: resource.instance.metadata.resourceVersion
        != starting_resource_version,
    )
    for sample in samplers:
        if sample:
            return True


def get_resource_object(resource, resource_name, resource_namespace):
    if "NamespacedResource" in str(resource.__base__):
        resource = resource(name=resource_name, namespace=resource_namespace)
    else:
        resource = resource(name=resource_name)
    assert resource.exists, f"Resource: {resource_name} not found."
    return resource


def get_resource_version_from_related_object(hco_related_objects, resource):
    for related_object in hco_related_objects:
        if related_object["kind"] == resource.kind:
            return related_object["resourceVersion"]
