#!/usr/bin/python
import json
import sys
from functools import partial
from os import getenv

from confluent_kafka import Consumer as KafkaConsumer
from dateutil import parser
from requests import get
from requests import post
from requests.auth import HTTPBasicAuth

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from lib.system_profile_validate import get_schema
from lib.system_profile_validate import get_schema_from_url
from lib.system_profile_validate import validate_sp_schemas


__all__ = "main"

LOGGER_NAME = "inventory_sp_validator"
REPO_OWNER = "RedHatInsights"
REPO_NAME = "inventory-schemas"
SP_SPEC_PATH = "schemas/system_profile/v1.yaml"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
GIT_USER = getenv("GIT_USER")
GIT_TOKEN = getenv("GIT_TOKEN")
VALIDATE_DAYS = int(getenv("VALIDATE_DAYS", 3))


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
        text += f"{reporter}:\n\tPass: {result.pass_count}\n\tFail: {result.fail_count}\n\n"
    return text


def _post_git_results_comment(pr_number, test_results):
    content = (
        f"Here are the System Profile validation results using Prod data.\n"
        f"Validating against the {REPO_OWNER}/{REPO_NAME} master spec:\n```\n"
        f"{_validation_results_plaintext(test_results[f'{REPO_OWNER}/{REPO_NAME}'])}\n```\n"
        f"Validating against this PR's spec:\n```\n"
        f"{_validation_results_plaintext(test_results['this'])}\n```\n"
    )
    response = _post_git_response(f"/repos/{REPO_OWNER}/{REPO_NAME}/issues/{pr_number}/comments", content)
    if response.status_code >= 400:
        logger.error(f"Could not post a comment to PR #{pr_number}. Response: {response.text}")
    else:
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


def _does_pr_require_validation(owner, repo, pr_number):
    latest_commit_datetime = _get_latest_commit_datetime_for_pr(owner, repo, pr_number)
    latest_self_comment_datetime = _get_latest_self_comment_datetime_for_pr(owner, repo, pr_number)
    sp_spec_modified = SP_SPEC_PATH in [
        file["filename"] for file in _get_git_response(f"/repos/{owner}/{repo}/pulls/{pr_number}/files")
    ]
    logger.debug(f"SP spec modified: {sp_spec_modified}")
    if sp_spec_modified and (
        latest_self_comment_datetime is None or latest_commit_datetime > latest_self_comment_datetime
    ):
        logger.info(f"- PR #{pr_number} requires validation!")
        return True
    else:
        logger.info(f"- PR #{pr_number} does not need validation.")

    return False


def _get_prs_that_require_validation(owner, repo):
    logger.info(f"Checking whether {owner}/{repo} PRs need schema validation...")
    prs_to_validate = []

    for pr_number in [pr["number"] for pr in _get_git_response(f"/repos/{owner}/{repo}/pulls?state=open")]:
        if _does_pr_require_validation(owner, repo, pr_number):
            prs_to_validate.append(pr_number)

    return prs_to_validate


def main(logger):
    config = _init_config()

    # Get list of PRs that require validation
    logger.info("Starting validation check.")
    prs_to_validate = _get_prs_that_require_validation(REPO_OWNER, REPO_NAME)
    if len(prs_to_validate) == 0:
        logger.info("No PRs to validate! Exiting.")
        sys.exit(0)

    # For each PR in prs_to_validate, validate the parsed hosts and leave a comment on the PR
    for pr_number in prs_to_validate:
        consumer = KafkaConsumer(
            {
                "bootstrap.servers": config.bootstrap_servers,
                **config.validator_kafka_consumer,
            }
        )

        sp_spec = None

        # Get spec file from PR
        file_list = _get_git_response(f"/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/files")
        for file in file_list:
            if file["filename"] == SP_SPEC_PATH:
                logger.debug(f"Getting SP spec from {file['raw_url']}")
                sp_spec = get_schema_from_url(file["raw_url"])
                break

        # If the System Profile spec wasn't modified, skip to the next PR.
        if not sp_spec:
            continue

        schemas = {f"{REPO_OWNER}/{REPO_NAME}": get_schema(REPO_OWNER, "master")}
        schemas["this"] = sp_spec

        try:
            test_results = validate_sp_schemas(
                consumer,
                [config.kafka_consumer_topic, config.additional_validation_topic],
                schemas,
                VALIDATE_DAYS,
                config.sp_validator_max_messages,
            )
            consumer.close()
        except ValueError as ve:
            logger.exception(ve)
            consumer.close()
            sys.exit(1)

        # Only post a comment if there still isn't one on the PR.
        # This is needed because another validation job may have posted a comment in the meantime.
        if _does_pr_require_validation(REPO_OWNER, REPO_NAME, pr_number):
            _post_git_results_comment(pr_number, test_results)

    logger.info("The validator has finished. Bye!")
    sys.exit(0)


if __name__ == "__main__":
    configure_logging()

    logger = get_logger(LOGGER_NAME)
    sys.excepthook = partial(_excepthook, logger)

    threadctx.request_id = None
    main(logger)
