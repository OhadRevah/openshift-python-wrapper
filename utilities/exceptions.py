class CommandExecFailed(Exception):
    def __init__(self, name, err=None):
        self.name = name
        self.err = f"Error: {err}" if err else ""

    def __str__(self):
        return f"Command: {self.name} - exec failed. {self.err}"


class UtilityPodNotFoundError(Exception):
    def __init__(self, node):
        self.node = node

    def __str__(self):
        return f"Utility pod not found for node: {self.node}"


class CommonNodesCpusNotFoundError(Exception):
    def __init__(self, nodes):
        self.nodes = [node.name for node in nodes]

    def __str__(self):
        return f"No common CPU models found across the nodes: {self.nodes}"


class ResourceValueError(Exception):
    pass


class ResourceMissingFieldError(Exception):
    pass
