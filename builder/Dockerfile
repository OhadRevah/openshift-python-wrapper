FROM quay.io/centos/centos:stream8

RUN yum -y install epel-release
RUN yum -y install --setopt=skip_missing_names_on_install=False \
python3-pip \
python3-devel \
procps-ng \
rsync \
gcc \
git \
libcurl-devel \
libxslt-devel \
libxml2-devel \
openssl-devel

RUN pip3 install pipenv

COPY / cnv-tests/
WORKDIR cnv-tests

ENV PIPENV_VENV_IN_PROJECT=1
ENV CNV_TESTS_CONTAINER=Yes
ENV PATH "$PATH:/mnt/host"

ARG OPENSHIFT_PYTHON_WRAPPER_COMMIT

RUN pipenv install --skip-lock
RUN pipenv run pip freeze
RUN if [[ -n "${OPENSHIFT_PYTHON_WRAPPER_COMMIT}" ]]; then pipenv run pip install git+https://github.com/RedHatQE/openshift-python-wrapper.git@$OPENSHIFT_PYTHON_WRAPPER_COMMIT -U; fi

CMD pipenv run pytest --tc=server_url:"$HTTP_IMAGE_SERVER" --collect-only
