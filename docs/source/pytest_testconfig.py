from collections import defaultdict


class FakeDict(defaultdict):
    """
    Class to return fake values for non exist values in dict
    """

    def as_list(self, key):
        value = [key]
        if isinstance(value, list):
            return value * 10
        elif isinstance(value, str):
            return value.split(",")
        return [value] * 10

    def as_int(self, key):
        return int(key)

    def as_bool(self, key):
        return True


config = FakeDict(lambda: "fake_value")
