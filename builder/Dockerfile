FROM quay.io/centos/centos:stream8

ENV PIPENV_VENV_IN_PROJECT=1 \
    CNV_TESTS_CONTAINER=Yes \
    PATH="$PATH:/mnt/host"

ARG OPENSHIFT_PYTHON_WRAPPER_COMMIT

RUN dnf -y install epel-release \
    && dnf -y install \
        python3-pip \
        python3-devel \
        procps-ng \
        rsync \
        gcc \
        git \
        wget \
        libcurl-devel \
        libxslt-devel \
        libxml2-devel \
        openssl-devel \
    && dnf clean all

COPY / cnv-tests/
WORKDIR cnv-tests

RUN pip3 install pipenv \
    && pipenv install --skip-lock \
    && pipenv run pip freeze \
    && if [[ -n "${OPENSHIFT_PYTHON_WRAPPER_COMMIT}" ]]; then pipenv run pip install git+https://github.com/RedHatQE/openshift-python-wrapper.git@$OPENSHIFT_PYTHON_WRAPPER_COMMIT -U; fi

CMD pipenv run pytest --tc=server_url:"$HTTP_IMAGE_SERVER" --collect-only
