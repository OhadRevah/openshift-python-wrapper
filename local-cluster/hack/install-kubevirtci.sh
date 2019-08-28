#!/bin/bash -e

commit="93616a62834cc35d1fa74b118f23320408038952"

script_dir=$(dirname "$(readlink -f "$0")")
kubevirtci_dir=local-cluster/kubevirtci

rm -rf $kubevirtci_dir
git clone https://github.com/kubevirt/kubevirtci $kubevirtci_dir
pushd $kubevirtci_dir
git checkout $commit
popd
