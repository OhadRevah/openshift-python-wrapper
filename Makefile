# Pytest args handling
PYTEST_ARGS ?= tests

ifdef UPSTREAM
	override PYTEST_ARGS += --tc-file=tests/global_config_upstream.py --tc-format=python
endif
ifndef UPSTREAM
	override PYTEST_ARGS += --tc-file=tests/global_config.py --tc-format=python
endif

#OPENSHIFT_PYTHON_WRAPPER LOG LEVEL
export OPENSHIFT_PYTHON_WRAPPER_LOG_LEVEL=DEBUG

# Local cluster preparations
CLUSTER_DIR := local-cluster/_hco
export KUBEVIRT_PROVIDER ?= k8s-1.21
export KUBEVIRT_NUM_NODES ?= 2
export KUBEVIRT_NUM_SECONDARY_NICS ?= 4
export KUBEVIRT_WITH_CNAO=true
export VIRTCTL_VERSION ?=v0.36.0

# Helper scripts
HACK_DIR := local-cluster/hack
CLUSTER_UP := $(HACK_DIR)/cluster-up.sh
CLUSTER_DOWN := $(HACK_DIR)/cluster-down.sh
VIRTCTL := $(HACK_DIR)/install-virtctl.sh

# If not specified otherwise, local cluster's KUBECONFIG will be used
export KUBECONFIG ?= $(CLUSTER_DIR)/_kubevirtci/_ci-configs/$(KUBEVIRT_PROVIDER)/.kubeconfig

# virtctl binary
BIN_DIR := local-cluster/_out/bin
VIRTCTL_DEST := $(BIN_DIR)

# Expose local binaries to tests
export PATH := $(BIN_DIR):$(PATH)

# Building cnv-tests container for disconnected clusters
IMAGE_BUILD_CMD ?= "docker"
IMAGE_REGISTRY ?= "quay.io"
REGISTRY_NAMESPACE ?= "openshift-cnv"
OPERATOR_IMAGE_NAME="cnv-tests"
# Need to change when master point to new version of cnv-tests
IMAGE_TAG ?= "4.11"

FULL_OPERATOR_IMAGE ?= "$(IMAGE_REGISTRY)/$(REGISTRY_NAMESPACE)/$(OPERATOR_IMAGE_NAME):$(IMAGE_TAG)"

all: check

check:
	tox

pipenv:
	-pipenv --rm # '-' for ignore error when pipenv venv is not exists
	pipenv install --skip-lock
	pipenv run pip freeze


tests: virtctl pipenv
	pipenv run pytest $(PYTEST_ARGS)

ci-tests: virtctl pipenv
	pipenv run pytest --tc-file=tests/global_config_ci.py --tc-format=python --log-collector --junit-xml xunit_results.xml --cluster-sanity-skip-check --skip-deprecated-api-test -s -m ci

cluster-down: $(CLUSTER_DOWN)
	$(CLUSTER_DOWN)

cluster-up: cluster-down $(CLUSTER_UP)
	$(CLUSTER_UP)

cluster-tests: cluster-up tests cluster-down
cluster-tests-ci: cluster-up ci-tests cluster-down

virtctl:
	mkdir -p $(BIN_DIR)
	VIRTCTL_DEST=$(BIN_DIR)/virtctl $(VIRTCTL)

build-container:
	$(IMAGE_BUILD_CMD) build --no-cache -f builder/Dockerfile -t $(FULL_OPERATOR_IMAGE) .

push-container:
	$(IMAGE_BUILD_CMD) push $(FULL_OPERATOR_IMAGE)

.PHONY: \
	check \
	cluster-down \
	cluster-up \
	cluster-tests \
	cluster-tests-ci \
	ci-tests \
	tests \
	build-container \
	push-container
