import json
import sys
from functools import partial
from os import getenv

from dateutil import parser
from kafka import KafkaConsumer
from requests import get
from requests import post
from requests.auth import HTTPBasicAuth

from app import UNKNOWN_REQUEST_ID_VALUE
from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from lib.system_profile_validate import get_hosts_from_kafka_messages
from lib.system_profile_validate import get_schema_from_url
from lib.system_profile_validate import validate_host_list_against_spec


__all__ = "main"

LOGGER_NAME = "inventory_sp_validator"
REPO_OWNER = "RedHatInsights"
REPO_NAME = "inventory-schemas"
SP_SPEC_PATH = "schemas/system_profile/v1.yaml"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
GIT_USER = getenv("GIT_USER")
GIT_TOKEN = getenv("GIT_TOKEN")
VALIDATE_DAYS = getenv("VALIDATE_DAYS", 3)


def _init_config():
    config = Config(RUNTIME_ENVIRONMENT)
    config.log_configuration()
    return config


def _excepthook(logger, type, value, traceback):
    logger.exception("System Profile Validator failed", exc_info=value)


def _get_git_response(path):
    return json.loads(
        get(f"https://api.github.com{path}", auth=HTTPBasicAuth(GIT_USER, GIT_TOKEN)).content.decode("utf-8")
    )


def _post_git_response(path, content):
    return post(f"https://api.github.com{path}", auth=HTTPBasicAuth(GIT_USER, GIT_TOKEN), json={"body": content})


def _validation_results_plaintext(test_results):
    text = ""
    for reporter, result in test_results.items():
        text += f"{reporter}:\n\tPass:{result.pass_count}\n\tFail:{result.fail_count}\n\t"
    return text


def _post_git_results_comment(pr_number, control_results, test_results):
    content = (
        f"Here are the System Profile validation results using the past {VALIDATE_DAYS} days of data.\n"
        f"Validating against the {REPO_OWNER}/{REPO_NAME} master spec:\n```\n"
        f"{_validation_results_plaintext(control_results)}\n```\n"
        f"Validating against this PR's spec:\n```\n"
        f"{_validation_results_plaintext(test_results)}\n```\n"
    )
    response = _post_git_response(f"/repos/{REPO_OWNER}/{REPO_NAME}/issues/{pr_number}/comments", content)
    logger.info(f"Posted a comment to PR #{pr_number}, with response status {response.status_code}")


def _get_latest_commit_datetime_for_pr(owner, repo, pr_number):
    pr_commits = _get_git_response(f"/repos/{owner}/{repo}/pulls/{pr_number}/commits")
    latest_commit = pr_commits[-1]
    return parser.isoparse(latest_commit["commit"]["author"]["date"])


def _get_latest_self_comment_datetime_for_pr(owner, repo, pr_number):
    pr_comments = _get_git_response(f"/repos/{owner}/{repo}/issues/{pr_number}/comments")
    for comment in reversed(pr_comments):
        if comment["user"]["login"] == GIT_USER:
            return parser.isoparse(comment["created_at"])
    return None


def _get_prs_that_require_validation(owner, repo):
    logger.info(f"Checking whether {owner}/{repo} PRs need schema validation...")
    prs_to_validate = []

    for pr_number in [pr["number"] for pr in _get_git_response(f"/repos/{owner}/{repo}/pulls?state=open")]:
        latest_commit_datetime = _get_latest_commit_datetime_for_pr(owner, repo, pr_number)
        latest_self_comment_datetime = _get_latest_self_comment_datetime_for_pr(owner, repo, pr_number)
        sp_spec_modified = SP_SPEC_PATH in [
            file["filename"] for file in _get_git_response(f"/repos/{owner}/{repo}/pulls/{pr_number}/files")
        ]
        logger.info(f"SP spec modified: {sp_spec_modified}")
        if sp_spec_modified and (
            latest_self_comment_datetime is None or latest_commit_datetime > latest_self_comment_datetime
        ):
            logger.info(f"- PR #{pr_number} requires validation!")
            prs_to_validate.append(pr_number)
        else:
            logger.info(f"- PR #{pr_number} does not need validation.")

    return prs_to_validate


def main(logger):

    config = _init_config()

    # Get list of PRs that require validation
    logger.info("Starting validation check.")
    prs_to_validate = _get_prs_that_require_validation(REPO_OWNER, REPO_NAME)
    if len(prs_to_validate) == 0:
        logger.info("No PRs to validate! Exiting.")
        sys.exit(0)

    # Get the list of parsed hosts from the last VALIDATE_DAYS worth of Kafka messages
    consumer = KafkaConsumer(
        group_id=config.host_ingress_consumer_group,
        bootstrap_servers=config.bootstrap_servers,
        api_version=(0, 10, 1),
        value_deserializer=lambda m: m.decode(),
        **config.kafka_consumer,
    )

    try:
        parsed_hosts = get_hosts_from_kafka_messages(consumer, VALIDATE_DAYS)
        consumer.close()
    except ValueError as ve:
        logger.error(ve)
        consumer.close()
        sys.exit(1)

    # For each PR in prs_to_validate, validate the parsed hosts and leave a comment on the PR
    for pr_number in prs_to_validate:
        # Get spec file from PR
        file_list = _get_git_response(f"/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/files")
        for file in file_list:
            if file["filename"] == SP_SPEC_PATH:
                logger.info(f"Getting SP spec from {file['raw_url']}")
                sp_spec = get_schema_from_url(file["raw_url"])
                break

        control_results = validate_host_list_against_spec(
            parsed_hosts,
            get_schema_from_url(
                f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/" f"master/schemas/system_profile/v1.yaml"
            ),
        )
        test_results = validate_host_list_against_spec(parsed_hosts, sp_spec)

        _post_git_results_comment(pr_number, control_results, test_results)

    logger.info("The validator has finished. Bye!")
    sys.exit(0)


if __name__ == "__main__":
    configure_logging()

    logger = get_logger(LOGGER_NAME)
    sys.excepthook = partial(_excepthook, logger)

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    main(logger)
