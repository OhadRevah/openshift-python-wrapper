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
RUN pipenv install --skip-lock
RUN pipenv run pip freeze
ENV CNV_TESTS_CONTAINER=Yes
ENV PATH "$PATH:/mnt/host"

CMD pipenv run pytest --tc=server_url:"$HTTP_IMAGE_SERVER" --collect-only
