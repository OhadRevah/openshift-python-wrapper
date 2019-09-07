#!/usr/bin/env bash

function finish {
    echo "Killing proxy (pid=$proxy_pid)..."
    kill $proxy_pid
}

function finalize_url {
    nsname=$1
    echo "http://localhost:$PORT/api/v1/namespaces/$nsname/finalize"
}

function patch {
    namespace=$1

    # the recipe is to completely remove status and clear spec attribute, as
    # described in: https://github.com/kubernetes/kubernetes/issues/60807
    data="$(kubectl get namespace $namespace -o json)"
    if [ $? != 0 ]; then
        return 1
    fi

    data="$(echo $data | jq 'del(.status) + {spec: {}}')"
    curl --silent \
        -H "Content-Type: application/json" \
        -X PUT \
        --data-binary "$data" \
        $(finalize_url $namespace)
}

function wait_until_deleted {
    kubectl wait --for=delete namespace/$1
}

namespace=$1

if [ -z "$namespace" ]; then
    echo "Usage: $0 nsname"
    exit 1
fi

PORT=9999
kubectl proxy -p $PORT &
proxy_pid=$!

trap finish EXIT

nsname=$1
{ patch $nsname && wait_until_deleted $nsname; } || true
exit 0
