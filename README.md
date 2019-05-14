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
