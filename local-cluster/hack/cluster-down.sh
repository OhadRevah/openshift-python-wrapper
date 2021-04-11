#!/bin/bash -e

script_dir=$(dirname "$(readlink -f "$0")")
hco_dir=local-cluster/_hco

if [ -d $hco_dir ]
then
    pushd $hco_dir
    make cluster-down
    popd
fi
