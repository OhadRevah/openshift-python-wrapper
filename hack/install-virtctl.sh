#!/bin/bash -e

VIRTCTL_BIN_SOURCE=https://github.com/kubevirt/kubevirt/releases/download/v0.19.0/virtctl-v0.19.0-linux-amd64

wget ${VIRTCTL_BIN_SOURCE} -O ${VIRTCTL_DEST}
chmod +x ${VIRTCTL_DEST}
