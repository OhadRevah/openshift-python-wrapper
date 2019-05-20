# cnv-tests
This repository contains tests. These tests are to verify functionality for OpenShift + CNV installation.

# Getting started
### Login to your OpenShift instance
```
oc login -u user -p password or set KUBECONFIG=<kubeconfig file> 
```
### Prepare the environment
```
    sudo dnf install pipenv
    pipenv --three install
```
### Running the tests

The simplest way to run the tests is as follows:
```
    pipenv run pytest tests \
    --tc-file=tests/test-config.yaml \
    --tc-format=yaml
```

If you target a cluster that is deployed using upstream manifests for HCO, you
may want to instead use a different test configuration file (also included with
the repository):
```
    pipenv run pytest tests \
    --tc-file=tests/test-config-upstream.yaml \
    --tc-format=yaml
```

There are other parameters that can be passed to the test suite if needed.

```
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

### network Utility container

Dockerfile is under `tests/manifests/network/privileged_container`

This image is created as a daemonset when the tests start and contains CLI commands
necessary to control network components on the tests environment hosts.

To build the image:
```bash
cd tests/manifests/network/privileged_container
docker build -t quay.io/redhat/cnv-tests-net-util-container .
docker login quay.io # Need to have right to push under the redhat organization
docker push quay.io/redhat/cnv-tests-net-util-container
```

### Development

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
