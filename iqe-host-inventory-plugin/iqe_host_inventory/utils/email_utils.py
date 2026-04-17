from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from iqe_bindings.v7.integrations_v1 import Endpoint
from iqe_bindings.v7.integrations_v1.exceptions import ApiException

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@dataclass
class FindEmailOptions:
    subject_token: str = ""
    recipient_token: str = ""
    time_token: str = ""
    body_token: str = ""
    retry: int = 3
    retry_timeout: int = 15
    retry_timeout_bump: bool = False
    retry_timeout_bump_amount: int = 30
    email_amount: int = 40


@dataclass(frozen=True)
class EmailEntity:
    id: str
    body: str
    headers: dict[str, list[str]]

    @property
    def template(self) -> BeautifulSoup:
        return BeautifulSoup(self.body, "lxml")

    @property
    def to_stage(self) -> bool:
        return any("webdev-spam-list" in h for h in self.headers.get("To", []))


class Email:
    def __init__(self, host_inventory: ApplicationHostInventory):
        self._host_inventory = host_inventory
        app = host_inventory.application

        if isinstance(app.user, Mapping) and "email_account" in app.user:
            self._config = app.user["email_account"]
        else:
            self._config = host_inventory.config.email_account.get("insights-qe")

    def _fetch_email_integration(self, only_admins: bool = False) -> Endpoint:
        client = self._host_inventory.v7_integrations_v1.default_api

        try_create = client.endpoint_resource_v1_get_or_create_email_subscription_endpoint(
            request_system_subscription_properties={"only_admins": only_admins}
        )
        try:
            client.endpoint_resource_v1_get_endpoint(try_create.id)
            return try_create
        except ApiException as e:
            if e.status != 404:
                raise

        try_get = client.endpoint_resource_v1_get_endpoints(type=["email_subscription"])
        for endpoint in try_get.data:
            if endpoint.properties.get("only_admins") != only_admins:
                continue
            try:
                client.endpoint_resource_v1_get_endpoint(endpoint.id)
                return endpoint
            except ApiException as e:
                if e.status == 404:
                    continue

        raise RuntimeError(
            f"No valid email_subscription endpoint found (only_admins={only_admins})"
        )

    def create_sample_integration(self) -> Endpoint:
        return self._fetch_email_integration(only_admins=False)

    @property
    def config(self):
        return self._config

    @property
    def credentials(self):
        token = self.config.get("token") if self.config else None
        if not token:
            raise ValueError(
                "Email credential 'token' is missing or empty in the config. "
                "Ensure the email_account config contains a valid JSON-encoded 'token' field."
            )
        try:
            token_info = json.loads(token)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Email credential 'token' is not valid JSON: {e}") from e

        creds = Credentials.from_authorized_user_info(token_info)

        if creds and creds.expired:
            log.info("Refreshing the token...")
            creds.refresh(Request())
        return creds

    @cached_property
    def _gmail_service(self):
        return build("gmail", "v1", credentials=self.credentials)

    def receive_emails(self, maxResults: int = 200, subject: str = ""):
        query = f'subject:"{subject}"' if subject else None
        resp = (
            self._gmail_service
            .users()
            .messages()
            .list(userId="me", maxResults=maxResults, q=query)
            .execute()
        )
        return resp.get("messages", [])

    def fetch_email(self, email_id: str):
        content = self._gmail_service.users().messages().get(userId="me", id=email_id).execute()
        return content

    def decode_body(self, content):
        body = content["payload"]["body"]["data"].replace("-", "+").replace("_", "/")
        raw = base64.b64decode(body)
        decoded_body = raw.decode("utf-8", errors="replace")
        return decoded_body

    def parse_headers(self, headers: list) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for h in headers:
            result.setdefault(h["name"], []).append(h["value"])
        return result

    def _matches_tokens(self, options: FindEmailOptions, body: str, headers: dict) -> bool:
        if options.subject_token and not any(
            options.subject_token in s for s in headers.get("Subject", [])
        ):
            return False
        if options.recipient_token and not any(
            options.recipient_token in rcpt for rcpt in headers.get("Delivered-To", [])
        ):
            return False
        if options.time_token and not any(
            options.time_token in d for d in headers.get("Date", [])
        ):
            return False
        return not (options.body_token and options.body_token not in body)

    def find_email(
        self,
        options: FindEmailOptions | None = None,
    ) -> EmailEntity | None:
        """Tries to find an email based on different tokens."""
        if options is None:
            options = FindEmailOptions()
        log.info(f"Will now try to find an email that matches {options} options...")

        delay = options.retry_timeout

        for i in range(options.retry):
            log.info(f"Fetching emails. Iteration {i}")
            mails = self.receive_emails(
                maxResults=options.email_amount, subject=options.subject_token
            )
            for mail in mails:
                content = self.fetch_email(mail["id"])
                payload = content["payload"]
                all_headers = self.parse_headers(payload["headers"])
                head_msg_id = all_headers.get("Message-ID")
                head_subject = all_headers.get("Subject")
                head_date = all_headers.get("Date")
                log.info(f"Trying email {head_date}: {head_msg_id} - {head_subject}")

                try:
                    body = self.decode_body(content)
                except KeyError:
                    log.info(f"Couldn't decode body of email {mail['id']}")
                    continue

                if not self._matches_tokens(options, body, all_headers):
                    continue

                log.info(f"Found email that matches tokens: {mail['id']} | {head_msg_id}")
                return EmailEntity(mail["id"], body, all_headers)
            if delay > 0:
                log.info(f"Waiting {delay} seconds before fetching new emails...")
                time.sleep(delay)
                if options.retry_timeout_bump:
                    delay += options.retry_timeout_bump_amount
        return None
