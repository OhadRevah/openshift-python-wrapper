#!/bin/bash -e

commit="c7a1f8d14f722e911798f27bfc7511e94f6f2392"

script_dir=$(dirname "$(readlink -f "$0")")
kubevirtci_dir=local-cluster/kubevirtci

rm -rf $kubevirtci_dir
git clone https://github.com/kubevirt/kubevirtci $kubevirtci_dir
pushd $kubevirtci_dir
git checkout $commit
popd
