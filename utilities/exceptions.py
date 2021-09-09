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


class CommonCpusNotFoundError(Exception):
    def __init__(self, available_cpus):
        self.available_cpus = available_cpus

    def __str__(self):
        return f"Failed to find a common CPU for all nodes: {self.available_cpus}"
