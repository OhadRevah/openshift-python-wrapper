                                 # CNV Common templates
This repository contains CNV VM tests.
VM creation is done using CNV common templates.

- Current tests cover RHEL and Windows.
- The tests can only be executed on downstream as http_server is not available for upstream.
- Windows tests can be executed on bare metal only, as Windows VMs 
run slow on nested visualization.

## RHEL Tests
* Create VM
* Start VM
* Console connection to VM
* VM OS validation
* Domain label validation
* SSH connection to VM (including service creation)
* VM migration
* VM deletion

## Windows Tests 
* Create VM
* Start VM
* HyperV
* Domain label validation
* VM migration
* VM deletion

## Fedora Tests (on latest OS supported by common templates)
* Create VM
* Start VM
* Console connection to VM
* VM OS validation
* HyperV
* Domain label validation
* SSH connection to VM (including service creation)
* VM deletion