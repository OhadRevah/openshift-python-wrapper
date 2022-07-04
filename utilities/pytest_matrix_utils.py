"""
all function in this file must accept only matrix arg.
def foo_matrix(matrix):
    <customize matrix code>
    return matrix
"""

from utilities.infra import get_admin_client
from utilities.storage import is_snapshot_supported_by_sc


def snapshot_matrix(matrix):
    matrix_to_return = []
    for storage_class in matrix:
        if is_snapshot_supported_by_sc(
            sc_name=[*storage_class][0],
            client=get_admin_client(),
        ):
            matrix_to_return.append(storage_class)
    return matrix_to_return
