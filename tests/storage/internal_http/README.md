## Internal HTTP server

#### build:
```bash
cd tests/storage/internal_http
docker build -t quay.io/openshift-cnv/qe-cnv-tests-internal-http .
docker push quay.io/openshift-cnv/qe-cnv-tests-internal-http
```