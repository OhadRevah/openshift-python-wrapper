                                 # CNV Common templates
This repository contains CNV VM tests.
VM creation is done using CNV common templates.

- Current tests cover RHEL, Fedora and Windows.
- The tests can only be executed on downstream as http_server is not available for upstream.
- To run a subset of OS support tests (test_rhel_os_support or test_windows_os_support) for a specific version:
1. Find the available OS versions in global_config.py (keys of rhel_os_matrix or windows_os_matrix dicts)
2. Add the following to the test execution command line:
```bash
--rhel-os-matrix=<RHEL OS version> OR --windows-os-matrix=<Windows OS version>
```
- To execute a subset of the tests for ci verification:
1. Select one of the available OS versions in global_config.py
2. Select one of the available storage class names in global_config.py (under 'storage_class_matrix')
3. Add the following to the test execution command line, example:
```bash
--rhel-os-matrix=rhel-7-8 --storage_class_matrix=hostpath-provisioner
```

## RHEL Tests
* Create VM
* Start VM
* Console connection to VM
* VM OS validation
* Guest agent info check
* Domain label validation
* SSH connection to VM (including service creation)
* VM deletion
* VM migration
* VM tablet input device
* VM and VMI machine type

## Windows Tests
* Create VM
* Start VM
* Guest agent info check
* HyperV
* Domain label validation
* VM migration
* VM deletion
* VM tablet input device
* VM and VMI machine type

## Fedora Tests (on latest OS supported by common templates)
* Create VM
* Start VM
* Console connection to VM
* VM OS validation
* Guest agent info check
* HyperV
* Domain label validation
* SSH connection to VM (including service creation)
* VM deletion
* VM and VMI machine type
