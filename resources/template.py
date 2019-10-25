import json

from .resource import NamespacedResource


class Template(NamespacedResource):
    api_group = "template.openshift.io"
    singular_name = "template"

    class Labels:
        FLAVOR = "flavor.template.kubevirt.io"
        OS = "os.template.kubevirt.io"
        WORKLOAD = "workload.template.kubevirt.io"

    def process(self, **kwargs):
        instance_dict = self.instance.to_dict()
        params = instance_dict["parameters"]
        # filling the template parameters with given kwargs
        for param in params:
            try:
                param["value"] = kwargs[param["name"]]
            except KeyError:
                continue
        instance_dict["parameters"] = params
        r = json.dumps(instance_dict)
        body = json.loads(r)
        response = self.client.request(
            method="Post",
            path="/apis/template.openshift.io/v1/namespaces/openshift/processedtemplates",
            body=body,
        )
        return response.to_dict()["objects"]
