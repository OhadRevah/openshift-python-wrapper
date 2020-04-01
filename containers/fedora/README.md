# Prerequisite
Export the relevant Fedora version, fore example:
```bash
export FEDORA_VERSION=31
```

# Fedora VM container

Image can be download from https://alt.fedoraproject.org/cloud/
To create a Fedora VM container execute build.sh.

To execute the build script the following packages needed:

    cloud-utils
    docker (https://docs.docker.com/install/linux/docker-ce/fedora)
    virt-install
    qemu-img

build.sh get Fedora image as parameter, for example:
```bash
./build.sh Fedora-Cloud-Base-30-1.2.x86_64.qcow2 $FEDORA_VERSION
```

This will install:

    tcpdump
    qemu-guest-agent
    iperf3
    dmidecode
    nginx
    lldpad
    kernel-modules
    nmap
    dhcp
    stress
    sshpass
    podman

enable qemu-guest-agent and sshd services in the VM.
If extra packages needed add them in user-data file.

Once executed you should have a login prompt to the VM.
If extra steps needed login with username fedora and password fedora, execute whats needed.
When done shutdown the VM:
```bash
sudo shutdown -h now
```

The tar container will be located under "fedora_build" folder.


### push container
```bash
cd fedora_build
docker load -i fedora-$FEDORA_VERSION.tar
docker tag fedora:$FEDORA_VERSION quay.io/redhat/cnv-tests-fedora-staging:$FEDORA_VERSION
docker push quay.io/redhat/cnv-tests-fedora-staging:$FEDORA_VERSION
```

30 tag should changed based on the Fedora version.

### Verify
Change tests/manifests/vm-fedora.yaml to use cnv-tests-fedora-staging image
`image: quay.io/redhat/cnv-tests-fedora-staging`
Run the tests (cnv-tests).

Once verified push the image to quay.io/redhat/cnv-tests-fedora
```bash
docker tag fedora:$FEDORA_VERSION quay.io/redhat/cnv-tests-fedora:$FEDORA_VERSION
docker push quay.io/redhat/cnv-tests-fedora:$FEDORA_VERSION
```

### Push qcow image to HTTP servers
Push qcow2 image to EMEA and USA HTTP servers
```bash
scp fedora_build/Fedora-Cloud-Base-30-1.2.x86_64.qcow2 root@cnv-qe-server.scl.lab.tlv.redhat.com:/var/www/files/cnv-tests/fedora/
scp fedora_build/Fedora-Cloud-Base-30-1.2.x86_64.qcow2 root@cnv-qe-server.rhevdev.lab.eng.rdu2.redhat.com:/var/www/files/cnv-tests/fedora/
```
