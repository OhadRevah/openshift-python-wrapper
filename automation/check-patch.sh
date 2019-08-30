#!/bin/bash -e

python=python3

main() {
    TARGET="$0"
    TARGET="${TARGET#./}"
    TARGET="${TARGET%.*}"
    TARGET="${TARGET#*.}"
    echo "TARGET=$TARGET"

    export PATH="$PATH:/usr/local/bin"

    case "${TARGET}" in
        "check" )
            check
            ;;
        "hco-master" )
            hco
            ;;
        * )
            echo "Unknown target"
            exit 1
            ;;
        esac
}

check() {
    $python -m pip install tox
    make check
}

hco() {
    export UPSTREAM=1

    echo "Installing dependencies"
    $python -m pip install pipenv
    PIPENV_HIDE_EMOJIS=1 PIPENV_NOSPIN=1 $python -m pipenv --three install

    echo "Install local cluster"
    make cluster-up

    echo "Install HCO on the cluster"
    make cluster-install-hco

    echo "Collect tests blacklist"
    blacklist_args=""
    while read test; do
        blacklist_args="${blacklist_args} --deselect '${test}'"
    done < automation/test-blacklist.txt

    echo "Run tests"
    make cluster-tests PYTEST_ARGS="${blacklist_args}"
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"
