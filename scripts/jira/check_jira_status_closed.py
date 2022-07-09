import re

from jira import JIRA, JIRAError

from scripts.utils import all_python_files, get_connection_params, print_status


def jira_connection_params():
    return get_connection_params(conf_file_name="jira.cfg")


def get_jira_status(jira_id):
    connection_params = jira_connection_params()
    jira_connection = JIRA(
        token_auth=connection_params["token"],
        options={"server": connection_params["url"]},
    )
    return jira_connection.issue(id=jira_id).fields.status.name


def get_all_jiras_from_file(file_content):
    """
    Try to find all jira tickets in the file.
    Looking for the following patterns:
    - jira_id=CNV-12345  # call in is_jira_open
    - jira_id = CNV-12345  # when jira is constant
    - https://issues.redhat.com/browse/CNV-12345  # when jira is in a link in comments
    - pytest.mark.jira(CNV-12345)  # when jira is in a marker

    Args:
        file_content (str): The content of the file.

    Returns:
        list: A list of jira tickets.
    """
    _pytest_jira_marker_bugs = re.findall(
        r"pytest.mark.jira.*?(CNV-\d+)", file_content, re.DOTALL
    )
    _is_jira_open = re.findall(r"(?:jira_id=|.*jira.* = )(CNV-\d+)", file_content)
    _jira_url_jiras = re.findall(
        r"https://issues.redhat.com/browse/(CNV-\d+(?! <skip-jira-check>))",
        file_content,
    )
    return set(_pytest_jira_marker_bugs + _is_jira_open + _jira_url_jiras)


def main():
    closed_statuses = jira_connection_params()["resolved_statuses"]
    closed_jiras = {}
    jira_ids_with_errors = {}
    for filename in all_python_files():
        filename_for_key = re.findall(r"cnv-tests/.*", filename)[0]
        with open(filename, "r") as fd:
            for _jira in get_all_jiras_from_file(file_content=fd.read()):
                try:
                    jira_status = get_jira_status(jira_id=_jira)
                except JIRAError as exp:
                    jira_ids_with_errors.setdefault(filename_for_key, []).append(
                        f"{_jira} [{exp.text}]"
                    )
                    continue

                if jira_status in closed_statuses:
                    closed_jiras.setdefault(filename_for_key, []).append(
                        f"{_jira} [{jira_status}]"
                    )

    if closed_jiras:
        print(
            f"The following Jira tickets are closed and needs to be removed ({len(closed_jiras)}):"
        )
        print_status(status_dict=closed_jiras)

    if jira_ids_with_errors:
        print(f"The following Jira ids had errors ({len(jira_ids_with_errors)}):")
        print_status(status_dict=jira_ids_with_errors)

    if closed_jiras or jira_ids_with_errors:
        exit(1)


if __name__ == "__main__":
    main()
