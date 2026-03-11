#!/usr/bin/python3
import json
import sys
import time
from datetime import datetime
from functools import partial
from logging import Logger
from os import getenv

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
REPO_NAME = "insights-host-inventory"
SP_SPEC_PATH = "swagger/system_profile.spec.yaml"
GIT_USER = getenv("GIT_USER", "")
GIT_TOKEN = getenv("GIT_TOKEN", "")
VALIDATE_DAYS = int(getenv("VALIDATE_DAYS", 3))
GIT_MAX_RETRIES = int(getenv("GIT_MAX_RETRIES", 3))

logger = get_logger(LOGGER_NAME)


class _GitHubRateLimiter:
    """Tracks GitHub API rate limit state across all requests.

    Without this, each _get_git_response call manages retries independently.
    When iterating through PRs (each requiring 3+ API calls), tokens are
    consumed instantly after a reset, and a nested call can exhaust its own
    retry budget — crashing the whole job.  By sharing state globally we
    proactively wait *before* sending a request that would be rejected.
    """

    def __init__(self):
        self._remaining: int | None = None
        self._reset_timestamp: int | None = None
        self._limit: int | None = None

    @property
    def remaining(self) -> int | None:
        return self._remaining

    @property
    def limit(self) -> int | None:
        return self._limit

    def update_from_response(self, response: Response) -> None:
        try:
            remaining = response.headers.get("X-RateLimit-Remaining")
            reset_time = response.headers.get("X-RateLimit-Reset")
            limit = response.headers.get("X-RateLimit-Limit")

            if remaining is not None:
                self._remaining = int(remaining)
            if reset_time is not None:
                self._reset_timestamp = int(reset_time)
            if limit is not None:
                self._limit = int(limit)
        except ValueError:
            logger.warning("Non-numeric rate-limit header received; ignoring")

    def get_wait_seconds(self, response: Response | None = None) -> int | None:
        """Return how many seconds to wait, or None if no wait is needed."""
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return int(retry_after)
                except ValueError:
                    pass

        if self._remaining is not None and self._remaining <= 0 and self._reset_timestamp:
            wait = self._reset_timestamp - int(time.time()) + 1
            return max(wait, 1)

        return None

    def wait_if_needed(self) -> None:
        """Block until the rate-limit window resets (if we know it's exhausted)."""
        wait = self.get_wait_seconds()
        if wait and wait > 0:
            logger.info(f"Rate limit exhausted ({self._remaining} remaining). Waiting {wait}s for reset.")
            time.sleep(wait)
            self._remaining = None


_rate_limiter = _GitHubRateLimiter()


def _get_git_response(path: str, max_retries: int = GIT_MAX_RETRIES) -> dict:
    """Make a GET request to GitHub API with global rate-limit awareness."""
    _rate_limiter.wait_if_needed()

    for attempt in range(max_retries + 1):
        response = get(f"https://api.github.com{path}", auth=HTTPBasicAuth(GIT_USER, GIT_TOKEN))
        _rate_limiter.update_from_response(response)

        if _rate_limiter.remaining is not None and _rate_limiter.limit is not None:
            logger.debug(f"GitHub API rate limit: {_rate_limiter.remaining}/{_rate_limiter.limit} remaining")

        is_rate_limited = response.status_code == 429 or (
            response.status_code == 403 and "rate limit" in response.text.lower()
        )

        if is_rate_limited:
            wait_time = _rate_limiter.get_wait_seconds(response)
            if wait_time and attempt < max_retries:
                logger.warning(
                    f"GitHub API rate limit hit. Waiting {wait_time} seconds before retry "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"GitHub API rate limit exceeded after {max_retries} retries")
                raise RuntimeError(f"GitHub API rate limit exceeded: {response.text}")

        if response.status_code >= 400:
            logger.error(f"GitHub API request failed: {response.status_code} - {response.text}")
            raise RuntimeError(f"GitHub API request failed with status {response.status_code}: {response.text}")

        # Proactively wait after a successful response that exhausted the quota,
        # so the *next* caller doesn't immediately get a 403.
        if _rate_limiter.remaining is not None and _rate_limiter.remaining <= 0:
            _rate_limiter.wait_if_needed()

        return json.loads(response.content.decode("utf-8"))

    raise RuntimeError("GitHub API request failed: max retries exceeded")


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


def _get_latest_self_comment_datetime_for_pr(owner: str, repo: str, pr_number: str) -> datetime | None:
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
