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
export KUBEVIRT_VERSION=$(curl -s https://api.github.com/repos/kubevirt/kubevirt/releases | grep tag_name | sort -V | tail -1 | awk -F '"' '{print $4}')
curl -L -o virtctl https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/virtctl-${KUBEVIRT_VERSION}-linux-amd64
chmod +x virtctl
sudo mv virtctl /usr/bin
```

##oc

Copy oc from /bin/oc on the master to /usr/local/bin/
Or download `http://download.eng.bos.redhat.com/rcm-guest/puddles/RHAOS/AtomicOpenShift/4.2/latest/puddle.repo`
into /etc/yum.repos and install openshift-clients

##Setup VirtualEnv

```bash
pip3 install pipenv
pipenv install
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

### Kubevirtci Kubernetes provider

When you want to run the test on k8s (and not okd/ocp) provider, you need to make sure that the
cluster can reach outside world to fetch docker images. Usually all that is required is adding the
following like to your system `/etc/resolv.conf`:

```
nameserver 192.168.8.1
```

### Using custom cluster management binaries

If you need to use custom or system `kubectl` or `virtctl` instead of wrappers from `local-cluster`,
define `KUBECTL` and `VIRTCTL` environment variables to point to the binaries.


### Using emulated virtualization

If you want to use emulated virtualization in your cluster, define `VIRT_EMULATION=1` before you setup
HCO cluster (ie. before running `make cluster-install-hco`).


## Running the tests

The simplest way to run the tests is as follows for downstream or upstream
HCO deployment respectively:

```bash
make tests
make tests UPSTREAM=1
```

## Other parameters

### Logging
Log file 'pytest-tests.log' is generated with the full pytest output in cnv-tests root directory.
For each test failure cluster logs are collected and stored under 'tests-collected-info'.

To see verbose logging of a test run, add the following parameter:

```bash
make tests PYTEST_ARGS="-o log_cli=true"
```
To enable log-collctor set CNV_TEST_COLLECT_LOGS
```bash
export CNV_TEST_COLLECT_LOGS=1
```
Logs will be available under tests-collected-info/ folder.

### Selecting tests

To run a particular set of tests, you can use name pattern matching. For
example, to run all network related tests, do:

```bash
make tests PYTEST_ARGS="-k network"
```

### Upgrade tests
To run upgrade test pass --upgrade to pytest command.
```bash
--upgrade
```

### Other parameters

There are other parameters that can be passed to the test suite if needed.

```bash
--tc-file=tests/global_config.py
--tc-format=python
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

### Using pytest_jira

pytest_jira plugin allows you to link tests to existing tickets.
jira.cfg contains the default connection settings as well as a list
of "resolved_statuses".
To use the plugin during a test run, use '--jira'.
Issues are considered as resolved if their status appears in resolved_statuses.
You can mark a test to be skipped if a Jira issue is not resolved.
Example:
```
@pytest.mark.jira("CNV-1234", run=False)
```
You can mark a test to be marked as xfail if a Jira issue is not resolved.
Example:
```
@pytest.mark.jira("CNV-1234")
```

### Running tests using matrix fixtures

Matrix fixtures can be added in global_config.py.
You can run a test using a subset of a simple matrix (i.e flat list), example:
```bash
--bridge-device-matrix=linux-bridge
```

To run a test using a subset of a complex matrix (e.g list of dicts), you'll also need to add
the following to tests/conftest.py
- Add parser.addoption under pytest_addoption (the name must end with _matrix)

Multiple keys can be selected by passing them with ','

Example:
```bash
--storage-class-matrix=rook-ceph-block
--storage-class-matrix=rook-ceph-block,nfs
```

### Using matrix fixtures

Using matrix fixtures requires providing a scope.
Format:
```
<type>_matrix__<scope>__
```
Example:
```
storage_class_matrix__module__
storage_class_matrix__class__
```

# Network utility container

Dockerfile is under `tests/manifests/network/privileged_container`

This image is created as a daemonset when the tests start and contains CLI
commands necessary to control network components on the tests environment hosts.

To build the image:

```bash
docker build -t quay.io/openshift-cnv/qe-cnv-tests-net-util-container -f ./tests/network/Dockerfile.net-utility ./tests/network
docker login quay.io # Need to have right to push under the redhat organization
docker push quay.io/openshift-cnv/qe-cnv-tests-net-util-container
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
We use checks tools that are defined in .pre-commit-config.yaml file
To install pre-commit:
```bash
pip install pre-commit --user
```
pre-commit will try to fix the error.
If some error where fixed git add & git commit is needed again.

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

### Generate source docs
```bash
cd docs
make html
```
The HTML file location is:
docs/build/html/index.html


### Tweaks
##### unprivileged_client
To skip 'unprivileged_client' creation pass to pytest command:
--tc=no_unprivileged_client:True

##### ssh workers by fixture
workers_ssh_executors fixture need to ssh the workers
From the slave it will work since it used the default ssh key to connect
To use non default key:
```bash
export HOST_SSH_KEY=path.to.ssh_key
```

##### Resources and utilities installation
To use resources and utilities as independent python packages:
From cnv-tests dir
```bash
pip3 install . -U --user
```
Used by import resources and import utilities.


##### Known Issues
pycurl may fail with error:
ImportError: pycurl: libcurl link-time ssl backend (nss) is different from compile-time ssl backend (none/other)

To fix it:
```bash
export PYCURL_SSL_LIBRARY=nss # or openssl. depend on the error (link-time ssl backend (nss))
pipenv run pip uninstall pycurl
pipenv run pip install pycurl --no-cache-dir
```
