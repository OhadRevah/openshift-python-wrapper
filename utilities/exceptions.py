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
