import logging
import sys

from pylero.exceptions import PyleroLibException
from pylero.work_item import Requirement

from scripts.polarion.polarion_utils import PROJECT, git_diff_added_removed_lines


logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def has_verify():
    added_ids, removed_ids = git_diff_added_removed_lines()
    for _id in added_ids:
        try:
            return Requirement(project_id=PROJECT, work_item_id=_id)
        except PyleroLibException:
            LOGGER.error(f"{_id}: Is missing requirement")
            sys.exit(1)


if __name__ == "__main__":
    has_verify()
