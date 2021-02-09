#  Network constants
SRIOV = "sriov"

#  Time constants
TIMEOUT_10MIN = 10 * 60
TIMEOUT_60MIN = 60 * 60

#  OS constants
OS_LOGIN_PARAMS = {
    "rhel": {
        "username": "cloud-user",
        "password": "redhat",
    },
    "fedora": {
        "username": "fedora",
        "password": "fedora",
    },
    "centos": {
        "username": "centos",
        "password": "centos",
    },
    "cirros": {
        "username": "cirros",
        "password": "gocubsgo",
    },
    "alpine": {
        "username": "root",
        "password": None,
    },
    "win": {
        "username": "Administrator",
        "password": "Heslo123",
    },
}
