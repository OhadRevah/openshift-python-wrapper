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
./build.sh Fedora-Cloud-Base-30-1.2.x86_64.qcow2 <version>
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
docker load -i fedora-<version>.tar
docker tag fedora:<version> quay.io/redhat/cnv-tests-fedora-staging:<version>
docker push quay.io/redhat/cnv-tests-fedora-staging:<version>
```

30 tag should changed based on the Fedora version.

### Verify
Change tests/manifests/vm-fedora.yaml to use cnv-tests-fedora-staging image
`image: quay.io/redhat/cnv-tests-fedora-staging`
Run the tests (cnv-tests).

Once verified push the image to quay.io/redhat/cnv-tests-fedora
```bash
docker tag fedora:<version> quay.io/redhat/cnv-tests-fedora:<version>
docker push quay.io/redhat/cnv-tests-fedora:<version>
```
