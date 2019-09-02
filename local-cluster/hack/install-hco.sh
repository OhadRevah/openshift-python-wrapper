#!/bin/bash -e

set -x

HCO_NS='kubevirt-hyperconverged'
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
crds/mro.crd.yaml
'

# Create the namespaces for the HCO
if [[ $(${KUBECTL} get ns ${HCO_NS}) == '' ]]; then
    ${KUBECTL} create ns ${HCO_NS}
fi

# Create additional namespaces needed for HCO components
namespaces=('openshift' 'openshift-machine-api')
for namespace in ${namespaces[@]}; do
    if [[ $(${KUBECTL} get ns ${namespace}) == '' ]]; then
        ${KUBECTL} create ns ${namespace}
    fi
done

# Switch to the HCO namespace.
${KUBECTL} config set-context $(${KUBECTL} config current-context) --namespace=kubevirt-hyperconverged

# Create all resources of HCO and its operators
for resource in ${HCO_RESOURCES}; do
    ${KUBECTL} apply -f ${HCO_SOURCES}/deploy/${resource}
done

function wait_until_available() {
  ${KUBECTL} wait hyperconverged hyperconverged-cluster --for condition=Available --timeout=1m
  return $?
}

set +e
for i in {0..30}
do
  echo "Try Number: $i"
  wait_until_available
  [ $? -eq 0 ] && exit 0
done
set -e


${KUBECTL} get hyperconverged hyperconverged-cluster -o yaml
# TODO WIP, checking why linux-bridge CNI doesn't get up withing the timeout
${KUBECTL} get ds --all-namespaces -o yaml | grep bridge
${KUBECTL} describe ds -n linux-bridge
${KUBECTL} get pods --all-namespaces -o yaml | grep bridge
echo 'Timed out while waiting for HyperConverged to become ready'
exit 1

