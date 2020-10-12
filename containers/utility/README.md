#### utility container

This image is created as a daemonset when the tests start and contains CLI
commands necessary to control network components on the tests environment hosts.

To build the image:

```bash
docker build -t quay.io/openshift-cnv/qe-cnv-tests-net-util-container -f Dockerfile .
docker login quay.io # Need to have right to push under the redhat organization
docker push quay.io/openshift-cnv/qe-cnv-tests-net-util-container
```
