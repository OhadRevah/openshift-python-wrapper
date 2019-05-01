#!/bin/bash -e

PATH="$PATH:/usr/local/bin"

easy_install-3.6 pip
pip3 install tox
tox