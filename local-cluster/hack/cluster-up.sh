#!/bin/bash -e

script_dir=$(dirname "$(readlink -f "$0")")
hco_dir=local-cluster/_hco

rm -rf $hco_dir
git clone https://github.com/kubevirt/hyperconverged-cluster-operator.git $hco_dir
pushd $hco_dir
git checkout release-1.6
make cluster-up
make cluster-sync
popd
