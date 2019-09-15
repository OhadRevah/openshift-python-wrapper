# Fedora VM container

To create a Fedora VM container execute build.sh.

To execute the build script the following packages needed:

    cloud-utils
    docker (https://docs.docker.com/install/linux/docker-ce/fedora)
    virt-install
    qemu-img

build.sh get Fedora image as parameter, for example:
```
./build.sh Fedora-Cloud-Base-30-1.2.x86_64.qcow2 (https://download.fedoraproject.org/pub/fedora/linux/releases/30/Cloud/x86_64/images/Fedora-Cloud-Base-30-1.2.x86_64.qcow2)
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

and enable qemu-guest-agent service in the VM.
If extra packages needed add them in user-data file.

Once executed you should have a login prompt to the VM.
If extra steps needed login with username fedora and password fedora, execute whats needed.
When done shutdown the VM:
```
sudo shutdown -h now
```

The tar container will be located under "fedora_build" folder.


### push container
From "fedora_build" folder:
```
docker load -i fedora.tar
docker tag fedora:30 quay.io/redhat/cnv-tests-fedora-staging
docker push quay.io/redhat/cnv-tests-fedora-staging
```

30 tag should changed based on the Fedora version.

### Verify
Change tests/manifests/vm-fedora.yaml to use cnv-tests-fedora-staging image
`image: quay.io/redhat/cnv-tests-fedora-staging`
Run the tests (cnv-tests).

Once verified push the image to quay.io/redhat/cnv-tests-fedora
```
docker tag fedora:30 quay.io/redhat/cnv-tests-fedora:30
docker push quay.io/redhat/cnv-tests-fedora:30
```
