#!/bin/bash -e

set -x

HCO_VERSION='master'
HCO_SOURCES="https://raw.githubusercontent.com/kubevirt/hyperconverged-cluster-operator/${HCO_VERSION}"
HCO_RESOURCES='crds/hco.crd.yaml
crds/kubevirt.crd.yaml
crds/cdi.crd.yaml
crds/cna.crd.yaml
crds/common-template-bundles.crd.yaml
crds/node-labeller-bundles.crd.yaml
crds/template-validator.crd.yaml
crds/nodemaintenance.crd.yaml
crds/metrics-aggregation.crd.yaml
cluster_role.yaml
service_account.yaml
cluster_role_binding.yaml
operator.yaml
hco.cr.yaml
'

# Create the namespaces for the HCO
${KUBECTL} create ns kubevirt-hyperconverged

# Switch to the HCO namespace.
${KUBECTL} config set-context $(${KUBECTL} config current-context) --namespace=kubevirt-hyperconverged

# Create all resources of HCO and its operators
for resource in ${HCO_RESOURCES}; do
    ${KUBECTL} create -f ${HCO_SOURCES}/deploy/${resource}
done

# Wait for all components to become ready
# TODO: Wait for HCO once it exposes conditions
until ${KUBECTL} get networkaddonsconfig cluster; do sleep 15; done
${KUBECTL} wait networkaddonsconfig cluster --for condition=Ready --timeout=10m
until ${KUBECTL} get cdi cdi-hyperconverged-cluster; do sleep 15; done
${KUBECTL} wait cdi cdi-hyperconverged-cluster --for condition=Running  --timeout=10m
until ${KUBECTL} get kubevirt kubevirt-hyperconverged-cluster -n kubevirt-hyperconverged; do sleep 15; done
${KUBECTL} wait kubevirt kubevirt-hyperconverged-cluster --for condition=Ready -n kubevirt-hyperconverged --timeout=10m
