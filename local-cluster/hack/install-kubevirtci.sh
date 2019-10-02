#!/bin/bash -e

commit="6806f6bc0bb3689fa7f02c5ffe7277a80420f749"

script_dir=$(dirname "$(readlink -f "$0")")
kubevirtci_dir=local-cluster/kubevirtci

rm -rf $kubevirtci_dir
git clone https://github.com/kubevirt/kubevirtci $kubevirtci_dir
pushd $kubevirtci_dir
git checkout $commit
popd
