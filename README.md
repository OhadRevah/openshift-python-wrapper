# cnv-tests

This repository contains tests. These tests are to verify functionality of
OpenShift + CNV installation.

# Prerequirements

```bash
pip3 install pipenv
pipenv --three install
```

# Getting started

## Prepare CNV cluster

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

If you don't have a running CNV cluster, you can use
[HCO](https://github.com/kubevirt/hyperconverged-cluster-operator). Follow the
[Launching the HCO on a local cluster](https://github.com/kubevirt/hyperconverged-cluster-operator#launching-the-hco-on-a-local-cluster)
guide and then set `KUBECONFIG`:

```bash
KUBECONFIG=${GOPATH}/github.com/kubevirt/hyperconverged-cluster-operator/cluster/.kubeconfig
```

## Running the tests

The simplest way to run the tests is as follows:

```bash
pipenv run pytest tests \
  --tc-file=tests/test-config.yaml \
  --tc-format=yaml
```

If you target a cluster that is deployed using upstream manifests for HCO, you
may want to instead use a different test configuration file (also included with
the repository):

```bash
pipenv run pytest tests \
  --tc-file=tests/test-config-upstream.yaml \
  --tc-format=yaml
```

## Other parameters

### Logging

To see verbose logging of a test run, add the following parameter:

```bash
pipenv run pytest tests \
  ... \
  -o log_cli=true
```

### Selecting tests

To run a particular set of tests, you can use name pattern matching. For
example, to run all network related tests, do:

```bash
pipenv run pytest tests \
  ... \
  -k network
```

### Other parameters

There are other parameters that can be passed to the test suite if needed.

```bash
pipenv run pytest tests \
  --tc-file=tests/test-config.yaml \
  --tc-format=yaml \
  --junitxml /tmp/xunit_results.xml \
  --bugzilla \
  --bugzilla-url=<url> \
  --bugzilla-user=<username> \
  --bugzilla-password=<password> \
  --jira \
  --jira-url=<url>  \
  --jira-user=<username> \
  --jira-password=<password>  \
  --jira-no-ssl-verify \
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
cd tests/manifests/network/privileged_container
docker build -t quay.io/redhat/cnv-tests-net-util-container .
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

Code style must pass flake8-black.
The plugin: https://github.com/peterjc/flake8-black
How to install and use black tool: https://github.com/python/black

To check for PEP 8 issues locally run:

```bash
tox
```

## How-to verify your patch

Run the Jenkins job for cnv-tests: https://cnv-qe-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/job/test-pytest-ocp-4.1-cnv-2.0-cluster

Click on Build with Parameters.

Under SLAVE_LABEL choose 'cnv-executor-cnv-tests'.

Under REFS add you patch refs in format `refs/changes/<link>/<commit>/<patch set>`, like: `refs/changes/71/176971/4`.

Add the link of the passed job to the patch in Gerrit when verifying it.
