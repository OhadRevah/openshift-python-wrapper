# cnv-tests

This repository contains tests. These tests are to verify functionality of
OpenShift + CNV installation.

# Prerequirements

Following binaries are needed:

##jq
Install using sudo yum install

##virtctl

Install using the following cli commands:

```bash
export KUBEVIRT_VERSION=$(curl -s https://api.github.com/repos/kubevirt/kubevirt/releases|grep tag_name|sort -V | tail -1 | awk -F':'
curl -L -o virtctl https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/virtctl-${KUBEVIRT_VERSION}-linux-amd64
chmod +x virtctl
sudo mv virtctl /usr/bin
```bash

##oc

Copy oc from /bin/oc on the master to /usr/local/bin/
Or download `http://download.eng.bos.redhat.com/rcm-guest/puddles/RHAOS/AtomicOpenShift/4.2/latest/puddle.repo`
into /etc/yum.repos and install openshift-clients

##Setup VirtualEnv

```bash
pip3 install pipenv
pipenv --three install
```

# Getting started

## Prepare CNV cluster

This project runs tests against a cluster with running CNV instance. You can
use your own cluster or deploy a local one using attached scripts.

### Local cluster

Deploy Kubernetes cluster using kubevirtci and install upstream HCO on top of
it. This can be used during development, but the results should not be used
for patch verification.

NOTE: Local cluster runs OKD4 by default and due to that, it has high memory requirements.
      You may need 20 GB of memory or more to run the cluster.


```bash
UPSTREAM=1 make cluster-up cluster-install-hco # deploy okd 4.1 as default
UPSTREAM=1 KUBEVIRT_PROVIDER=k8s-1.13.3 make cluster-up cluster-install-hco # deploy on ks8 1.13.3
UPSTREAM=1 KUBEVIRT_PROVIDER=okd-4.1 make cluster-up cluster-install-hco # deploy on okd 4.1
```

### Arbitrary cluster

These tests can be executed against arbitrary OpenShift cluster with CNV
installed.

You can login into such cluster via:

```bash
oc login -u user -p password
```

Or by setting `KUBECONFIG` variable:

```bash
KUBECONFIG=<kubeconfig file>
```

## Running the tests

The simplest way to run the tests is as follows for downstream or upstream
HCO deployment respectively:

```bash
make tests
make tests UPSTREAM=1
```

## Other parameters

### Logging

To see verbose logging of a test run, add the following parameter:

```bash
make tests PYTEST_ARGS="-o log_cli=true"
```

### Selecting tests

To run a particular set of tests, you can use name pattern matching. For
example, to run all network related tests, do:

```bash
make tests PYTEST_ARGS="-k network"
```

### Other parameters

There are other parameters that can be passed to the test suite if needed.

```bash
--tc-file=tests/test-config.yaml
--tc-format=yaml
--junitxml /tmp/xunit_results.xml
--bugzilla
--bugzilla-url=<url>
--bugzilla-user=<username>
--bugzilla-password=<password>
--jira
--jira-url=<url>
--jira-user=<username>
--jira-password=<password>
--jira-no-ssl-verify
--jira-disable-docs-search
```

Note: some older versions of openshift-installer may have a bug where test
namespaces created by the suite are left stuck in Terminating state forever. In
this case, you may want to use the `clean-namespace.sh` script located in the
root directory of this repository.

# Network utility container

Dockerfile is under `tests/manifests/network/privileged_container`

This image is created as a daemonset when the tests start and contains CLI
commands necessary to control network components on the tests environment hosts.

To build the image:

```bash
docker build -t quay.io/redhat/cnv-tests-net-util-container -f ./tests/network/Dockerfile.net-utility ./tests/network
docker login quay.io # Need to have right to push under the redhat organization
docker push quay.io/redhat/cnv-tests-net-util-container
```

# Development

Development is happening using internal Red Hat Gerrit instance
(code.engineering.redhat.com). To interact with the server, please install
`git-review` on your system. More details here:
https://docs.openstack.org/infra/git-review/

At the moment of writing, automated CI is very limited for the repository, so
it's expected from authors of new patches to verify their changes are not
breaking the rest of the code, and if so, to mark them as Verified+1.
(Determining the depth of verification steps for each patch is left for the
author and their reviewer.) It's required that the procedure used to verify a
patch is listed in comments to the review request.

## How-to verify your patch

### Check the code

Code style must pass flake8-black.
The plugin: https://github.com/peterjc/flake8-black
How to install and use black tool: https://github.com/python/black

Code style must pass flake8-isort
The plugin: https://github.com/gforcada/flake8-isort
How to install and use isort: https://github.com/timothycrosley/isort/wiki/isort-Plugins

To get automatic black and isort check and fix on pre-commit:
```bash
pip install pre-commit --user
```
This will use .pre-commit-config.yaml configuration.

To check for PEP 8 issues locally run:

```bash
make check
```

### Run functional tests locally

It is possible to run functional tests on local 2-node Kubernetes environment.
This is not a targeted setup for users, but these tests may help you during the
development before proper verification described in the following section.

Run tests locally:

```bash
UPSTREAM=1 make cluster-up cluster-install-hco cluster-tests
```

Remove the cluster:

```bash
make cluster-down
```

### Run functional tests via an OCP Jenkins job

Run the Jenkins job for cnv-tests:
    Find the right job for you patch by cnv version/branch.
    branch cnv-2.0 will use `test-pytest-ocp-4.1-cnv-2.0-cluster`
    branch master will use `test-pytest-ocp-4.2-cnv-2.1-cluster` which is the latest cnv version.

https://cnv-qe-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/job/<job name based on patch branch>

Click on Build with Parameters.
Under `SLAVE_LABEL` choose 'cnv-executor-cnv-tests'.
Under `REFS` add you patch refs in format `refs/changes/<link>/<commit>/<patch set>`, like: `refs/changes/71/176971/4`.
    ref can be found under 'download' in the top right corner gerrit patch page.
    can be set multiple refs.
To pass parameters to pytest command add them to `PYTEST_PARAMS`.
    for example `-k 'network'` will run only tests that match 'network'

Add the link of the passed job to the patch in Gerrit when verifying it.
