#!/usr/bin/env bash
set -xe

BUILD_DIR="fedora_build"
FEDORA_IMAGE=$1
CLOUD_INIT_ISO="cidata.iso"
NAME="fedora${FEDORA_VERSION}"
mkdir $BUILD_DIR

echo "Create cloud-init user data ISO"
cloud-localds $CLOUD_INIT_ISO user-data

echo "Run the VM (ctrl+] to exit)"
virt-install \
  --memory 2048 \
  --vcpus 2 \
  --name $NAME \
  --disk $FEDORA_IMAGE,device=disk \
  --disk $CLOUD_INIT_ISO,device=cdrom \
  --os-type Linux \
  --os-variant $NAME \
  --virt-type kvm \
  --graphics none \
  --network default \
  --import

echo "Remove Fedora VM"
virsh destroy $NAME || :
virsh undefine $NAME

rm -rf $CLOUD_INIT_ISO

echo "Convert image"
qemu-img convert -c -O qcow2 $FEDORA_IMAGE $BUILD_DIR/$FEDORA_IMAGE

echo "Create Dockerfile"
echo "FROM kubevirt/container-disk-v1alpha" >> $BUILD_DIR/Dockerfile
echo "ADD $FEDORA_IMAGE /disk" >> $BUILD_DIR/Dockerfile

pushd $BUILD_DIR
echo "Build docker image"
docker build -t fedora:$FEDORA_VERSION .

echo "Save docker image as TAR"
docker save --output fedora-$FEDORA_VERSION.tar fedora
popd
echo "Fedora image locate at $BUILD_DIR"
