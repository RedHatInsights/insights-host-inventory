#!/usr/bin/python
import json
import sys
from datetime import datetime
from functools import partial
from logging import Logger
from os import getenv
from typing import Union

from confluent_kafka import Consumer as KafkaConsumer
from dateutil import parser
from requests import Response
from requests import get
from requests import post
from requests.auth import HTTPBasicAuth
from yaml import parser as yamlParser

from app.config import Config
from app.logging import get_logger
from app.logging import threadctx
from jobs.common import excepthook
from jobs.common import job_setup
from lib.system_profile_validate import TestResult
from lib.system_profile_validate import get_schema
from lib.system_profile_validate import get_schema_from_url
from lib.system_profile_validate import validate_sp_schemas

__all__ = "main"

PROMETHEUS_JOB = "inventory-sp-validator"
LOGGER_NAME = "inventory_sp_validator"
REPO_OWNER = "RedHatInsights"
REPO_NAME = "inventory-schemas"
SP_SPEC_PATH = "schemas/system_profile/v1.yaml"
GIT_USER = getenv("GIT_USER", "")
GIT_TOKEN = getenv("GIT_TOKEN", "")
VALIDATE_DAYS = int(getenv("VALIDATE_DAYS", 3))

logger = get_logger(LOGGER_NAME)


def _get_git_response(path: str) -> dict:
    return json.loads(
        get(f"https://api.github.com{path}", auth=HTTPBasicAuth(GIT_USER, GIT_TOKEN)).content.decode("utf-8")
    )


def _post_git_response(path: str, content: str) -> Response:
    return post(f"https://api.github.com{path}", auth=HTTPBasicAuth(GIT_USER, GIT_TOKEN), json={"body": content})


def _validation_results_plaintext(test_results: dict[str, TestResult]) -> str:
    text = ""
    for reporter, result in test_results.items():
        text += f"{reporter}:\n\tPass: {result.pass_count}\n\tFail: {result.fail_count}\n\n"
    return text


def _generate_comment_from_results(test_results: dict) -> str:
    return (
        f"Here are the System Profile validation results using Prod data.\n"
        f"Validating against the {REPO_OWNER}/{REPO_NAME} master spec:\n```\n"
        f"{_validation_results_plaintext(test_results[f'{REPO_OWNER}/{REPO_NAME}'])}\n```\n"
        f"Validating against this PR's spec:\n```\n"
        f"{_validation_results_plaintext(test_results['this'])}\n```\n"
    )


def _post_git_comment_to_pr(pr_number: str, content: str) -> None:
    response = _post_git_response(f"/repos/{REPO_OWNER}/{REPO_NAME}/issues/{pr_number}/comments", content)
    if response.status_code >= 400:
        logger.error(f"Could not post a comment to PR #{pr_number}. Response: {response.text}")
    else:
        logger.info(f"Posted a comment to PR #{pr_number}, with response status {response.status_code}")


def _get_latest_commit_datetime_for_pr(owner: str, repo: str, pr_number: str) -> datetime:
    pr_commits = _get_git_response(f"/repos/{owner}/{repo}/pulls/{pr_number}/commits")
    latest_commit = pr_commits[-1]
    return parser.isoparse(latest_commit["commit"]["author"]["date"])


def _get_latest_self_comment_datetime_for_pr(owner: str, repo: str, pr_number: str) -> Union[datetime, None]:
    pr_comments = _get_git_response(f"/repos/{owner}/{repo}/issues/{pr_number}/comments")
    for comment in reversed(pr_comments):
        if comment["user"]["login"] == GIT_USER:
            return parser.isoparse(comment["created_at"])
    return None


def _does_pr_require_validation(owner: str, repo: str, pr_number: str) -> bool:
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


def _get_prs_that_require_validation(owner: str, repo: str) -> list[str]:
    logger.info(f"Checking whether {owner}/{repo} PRs need schema validation...")
    prs_to_validate = []

    for pr_number in [pr["number"] for pr in _get_git_response(f"/repos/{owner}/{repo}/pulls?state=open")]:
        if _does_pr_require_validation(owner, repo, pr_number):
            prs_to_validate.append(pr_number)

    return prs_to_validate


def _get_sp_spec_from_pr(pr_number: str) -> dict:
    # Get spec file from PR
    file_list = _get_git_response(f"/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/files")
    for file in file_list:
        if file["filename"] == SP_SPEC_PATH:
            logger.debug(f"Getting SP spec from {file['raw_url']}")
            return get_schema_from_url(file["raw_url"])

    raise FileNotFoundError()


def _validate_schema_for_pr_and_generate_comment(pr_number: str, config: Config) -> str:
    consumer = KafkaConsumer(
        {
            "bootstrap.servers": config.bootstrap_servers,
            **config.validator_kafka_consumer,
        }
    )

    try:
        schemas = {
            f"{REPO_OWNER}/{REPO_NAME}": get_schema(REPO_OWNER, "master"),
            "this": _get_sp_spec_from_pr(pr_number),
        }
    except yamlParser.ParserError as pe:
        logger.error(pe)
        return (
            "An error occurred while trying to parse the schema in this PR. "
            "Please verify the syntax and formatting, and see the pod logs for further details."
        )

    try:
        test_results = validate_sp_schemas(
            consumer,
            [config.kafka_consumer_topic, config.additional_validation_topic],
            schemas,
            VALIDATE_DAYS,
            config.sp_validator_max_messages,
        )
        consumer.close()
        return _generate_comment_from_results(test_results)
    except ValueError as ve:
        logger.exception(ve)
        consumer.close()
        sys.exit(1)


def main(logger: Logger, config: Config):
    if config.replica_namespace:
        logger.info("Running in replica cluster - skipping schema validation")
        sys.exit(0)

    # Get list of PRs that require validation
    logger.info("Starting validation check.")
    prs_to_validate = _get_prs_that_require_validation(REPO_OWNER, REPO_NAME)
    if len(prs_to_validate) == 0:
        logger.info("No PRs to validate! Exiting.")
        sys.exit(0)

    # For each PR in prs_to_validate, validate the parsed hosts and leave a comment on the PR
    for pr_number in prs_to_validate:
        try:
            message = _validate_schema_for_pr_and_generate_comment(pr_number, config)
        except FileNotFoundError:
            # System Profile not changed in PR, no need to validate
            continue

        # Only post a comment if there still isn't one on the PR.
        # This check is needed because another validation job may have posted a comment in the meantime.
        if _does_pr_require_validation(REPO_OWNER, REPO_NAME, pr_number):
            _post_git_comment_to_pr(pr_number, message)

    logger.info("The validator has finished. Bye!")
    sys.exit(0)


if __name__ == "__main__":
    job_type = "System Profile Validator"
    sys.excepthook = partial(excepthook, logger, job_type)
    threadctx.request_id = None

    config, _, _, _, _, application = job_setup((), PROMETHEUS_JOB)
    with application.app.app_context():
        main(logger, config)
