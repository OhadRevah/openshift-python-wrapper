from resources.pod import Pod


class WinRMcliPod(Pod):
    def __init__(self, name, namespace, node_selector=None):
        super().__init__(name=name, namespace=namespace)
        self.node_selector = node_selector

    def _to_dict(self):
        res = super()._to_dict()
        res["spec"] = {
            "containers": [
                {
                    "name": "winrmcli-con",
                    "image": "kubevirt/winrmcli:latest",
                    "command": ["bash", "-c", "/usr/bin/sleep 6000"],
                }
            ]
        }
        if self.node_selector:
            res["spec"]["nodeSelector"] = {"kubernetes.io/hostname": self.node_selector}

        return res
