#!/bin/bash -e

commit="7ff84096b06a6a7d59ec83bfdf81be6f74a5c542"

script_dir=$(dirname "$(readlink -f "$0")")
kubevirtci_dir=kubevirtci

rm -rf $kubevirtci_dir
git clone https://github.com/kubevirt/kubevirtci $kubevirtci_dir
pushd $kubevirtci_dir
git checkout $commit
popd
