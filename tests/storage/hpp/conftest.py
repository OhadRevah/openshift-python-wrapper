import io

import pytest
import yaml
from ocp_resources.daemonset import DaemonSet

from utilities.infra import (
    cluster_resource,
    get_daemonset_yaml_file_with_image_hash,
    get_utility_pods_from_nodes,
)


@pytest.fixture
def utility_daemonset_for_hpp_test(is_upstream_distribution, generated_pulled_secret):
    """
    Deploy utility daemonset into the kube-system namespace.
    This daemonset deploys a pod on every node with hostNetwork and the main usage is to run commands on the hosts.
    """
    ds_yaml_file = get_daemonset_yaml_file_with_image_hash(
        is_upstream_distribution=is_upstream_distribution,
        generated_pulled_secret=generated_pulled_secret,
    )
    ds_yaml = yaml.safe_load(ds_yaml_file.read())
    utility_pods_for_hpp_test = "utility-pods-for-hpp-test"

    ds_yaml_metadata = ds_yaml["metadata"]
    ds_yaml_metadata["labels"]["cnv-test"] = utility_pods_for_hpp_test
    ds_yaml_metadata["name"] = utility_pods_for_hpp_test
    ds_yaml_spec = ds_yaml["spec"]
    ds_yaml_spec["selector"]["matchLabels"]["cnv-test"] = utility_pods_for_hpp_test
    ds_yaml_spec["template"]["metadata"]["labels"][
        "cnv-test"
    ] = utility_pods_for_hpp_test
    ds_yaml_spec["template"]["spec"]["containers"][0][
        "name"
    ] = utility_pods_for_hpp_test
    ds_yaml_file = io.StringIO(yaml.dump(ds_yaml))

    with cluster_resource(DaemonSet)(yaml_file=ds_yaml_file) as ds:
        ds.wait_until_deployed()
        yield ds


@pytest.fixture
def utility_pods_for_hpp_test(
    admin_client,
    workers,
    utility_daemonset_for_hpp_test,
):
    utility_pod_label = utility_daemonset_for_hpp_test.instance.metadata.labels[
        "cnv-test"
    ]
    return get_utility_pods_from_nodes(
        nodes=workers,
        admin_client=admin_client,
        label_selector=f"cnv-test={utility_pod_label}",
    )