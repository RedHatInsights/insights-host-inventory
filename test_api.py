#!/usr/bin/env python

import unittest
import json
from app import create_app, db
from app.auth import current_identity
from app.auth.identity import Identity
from app.utils import HostWrapper
from base64 import b64encode
from json import dumps

HOST_URL = "/api/hosts"

NS = "testns"
ID = "whoabuddy"

FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
TAGS = ["aws/new_tag_1:new_value_1", "aws/k:v"]

from unittest.mock import patch


class Request:
    headers = {"x-rh-identity": ""}


def from_encoded(payload):
    return None


def validate(identity):
    pass


def bypass_auth(func):
    patchers = [
        patch("app.auth.request", Request),
        patch("app.auth.from_encoded", from_encoded),
        patch("app.auth.validate", validate)
    ]

    for patcher in patchers:
        func = patcher(func)

    return func


def test_data(display_name="hi", canonical_facts=None, tags=None, facts=None):
    return {
        "account": "test",
        "display_name": display_name,
        "canonical_facts": canonical_facts if canonical_facts else {NS: ID},
        "tags": tags if tags else [],
        "facts": facts if facts else FACTS,
    }


class BaseAPITestCase(unittest.TestCase):

    def setUp(self):
        self.app = create_app(config_name="testing")
        self.client = self.app.test_client

        # binds the app to the current context
        with self.app.app_context():
            # create all tables
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            # drop all tables
            db.session.remove()
            db.drop_all()

    def get(self, path, status=200, return_response_as_json=True):
        return self._response_check(
            self.client().get(path), status, return_response_as_json
        )

    def post(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(
            self.client().post, path, data, status, return_response_as_json
        )

    def patch(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(
            self.client().patch, path, data, status, return_response_as_json
        )

    def put(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(
            self.client().put, path, data, status, return_response_as_json
        )

    def _make_http_call(
        self, http_method, path, data, status, return_response_as_json=True
    ):
        json_data = json.dumps(data)
        return self._response_check(
            http_method(
                path, data=json_data, headers={'content-type': 'application/json'}
            ),
            status,
            return_response_as_json,
        )

    def _response_check(self, response, status, return_response_as_json):
        self.assertEqual(response.status_code, status)
        if return_response_as_json:
            return json.loads(response.data)

        else:
            return response

    def _build_host_id_list_for_url(self, host_list):
        host_id_list = [str(h.id) for h in host_list]

        return ",".join(host_id_list)


@bypass_auth
class CreateHostsTestCase(BaseAPITestCase):

    def test_create_and_update(self):
        canonical_facts = {"test_id": "11-22-33", "another_test_id": "44-55-66"}
        facts = None
        tags = ["/merge_me_1:value1"]

        host_data = HostWrapper(
            test_data(canonical_facts=canonical_facts, facts=facts, tags=tags)
        )

        # initial create
        results = self.post(HOST_URL, host_data.data(), 201)

        self.assertIsNotNone(results["id"])

        original_id = results["id"]

        post_data = host_data
        post_data.facts = FACTS

        # Replace facts under the first namespace
        post_data.facts[0]["facts"] = {"newkey1": "newvalue1"}

        # Add a new set of facts under a new namespace
        post_data.facts.append({"namespace": "ns2", "facts":
                               {"key2": "value2"}})

        # Add a new canonical fact
        post_data.canonical_facts["test2"] = "test2id"

        # Add a new tag
        post_data.tags = ["aws/new_tag_1:new_value_1"]

        expected_tags = tags
        expected_tags.extend(post_data.tags)

        # update initial entity
        results = self.post(HOST_URL, post_data.data(), 200)

        self.assertEqual(results["id"], original_id)

        data = self.get("%s/%s" % (HOST_URL, original_id), 200)
        results = HostWrapper(data["results"][0])

        # sanity check
        # post_data.facts[0]["facts"]["key2"] = "blah"
        self.assertListEqual(results.facts, post_data.facts)

        # make sure the canonical facts are merged
        self.assertEqual(len(results.canonical_facts), 3)
        self.assertEqual(results.canonical_facts["test2"], "test2id")

        # make sure the tags are merged
        self.assertListEqual(results.tags, expected_tags)

    def test_create_host_with_empty_tags_facts_display_name_then_update(self):
        # Create a host with empty tags, facts, and display_name
        # then update those fields
        host_data = HostWrapper(test_data(facts=None))
        del host_data.tags
        del host_data.display_name
        del host_data.facts

        # initial create
        results = self.post(HOST_URL, host_data.data(), 201)

        self.assertIsNotNone(results["id"])

        original_id = results["id"]

        host_data.tags = ["aws/new_tag_1:new_value_1", "aws/k:v"]
        host_data.facts = FACTS
        host_data.display_name = "expected_display_name"

        self.post(HOST_URL, host_data.data(), 200)

        data = self.get("%s/%s" % (HOST_URL, original_id), 200)
        results = HostWrapper(data["results"][0])

        self.assertListEqual(results.tags, host_data.tags)

        self.assertListEqual(results.facts, host_data.facts)

        self.assertEqual(results.display_name, host_data.display_name)

    def test_create_host_without_canonical_facts(self):
        host_data = HostWrapper(test_data(facts=None))
        del host_data.canonical_facts

        # FIXME: Verify response?
        response_data = self.post(HOST_URL, host_data.data(), 400)

    def test_create_host_without_account(self):
        host_data = HostWrapper(test_data(facts=None))
        del host_data.account

        # FIXME: Verify response?
        response_data = self.post(HOST_URL, host_data.data(), 400)


class PreCreatedHostsBaseTestCase(BaseAPITestCase):

    def setUp(self):
        super(PreCreatedHostsBaseTestCase, self).setUp()
        self.added_hosts = self.add_2_hosts()

    @bypass_auth
    def add_2_hosts(self):
        # FIXME: make this more generic
        host_list = []

        canonical_facts = {'insights_id': '12345'}
        display_name = "host1"
        tags = TAGS
        host_data = HostWrapper(
            test_data(
                display_name=display_name, canonical_facts=canonical_facts, tags=tags
            )
        )
        response_data = self.post(HOST_URL, host_data.data(), 201)
        host_list.append(HostWrapper(response_data))

        canonical_facts = {'insights_id': '54321'}
        display_name = "host2"
        tags = TAGS
        host_data = HostWrapper(
            test_data(
                display_name=display_name, canonical_facts=canonical_facts, tags=tags
            )
        )
        response_data = self.post(HOST_URL, host_data.data(), 201)
        host_list.append(HostWrapper(response_data))

        return host_list


@bypass_auth
class QueryTestCase(PreCreatedHostsBaseTestCase):

    def test_query_all(self):
        response = self.get(HOST_URL, 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), len(self.added_hosts))

    def test_query_using_host_id_list(self):
        host_list = self.added_hosts

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        response = self.get(HOST_URL + "/" + url_host_id_list, 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    def test_query_using_single_tag(self):
        host_list = self.added_hosts

        response = self.get(HOST_URL + "?tag=" + TAGS[0], 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    def test_query_using_multiple_tags(self):
        response = self.get(HOST_URL + "?tag=" + TAGS[0] + "&tag=" + TAGS[1], 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    def test_query_using_display_name(self):
        host_list = self.added_hosts

        response = self.get(HOST_URL + "?display_name=" + host_list[0].display_name)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 1)

    def test_query_using_display_name_substring(self):
        host_list = self.added_hosts

        host_name_substr = host_list[0].display_name[:-2]

        response = self.get(HOST_URL + "?display_name=" + host_name_substr)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)


@bypass_auth
class FactsTestCase(PreCreatedHostsBaseTestCase):

    def _build_facts_url(self, host_list, namespace):
        if type(host_list) == list:
            url_host_id_list = self._build_host_id_list_for_url(host_list)
        else:
            url_host_id_list = str(host_list)
        return HOST_URL + "/" + url_host_id_list + "/facts/" + namespace

    def test_add_facts_without_fact_dict(self):
        patch_url = self._build_facts_url(1, "ns1")
        response = self.patch(patch_url, None, 400)
        self.assertEqual(response['detail'], "Request body is not valid JSON")

    def test_add_facts_to_multiple_hosts(self):
        facts_to_add = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

        host_list = self.added_hosts

        # This test assumes the set of facts are the same across
        # the hosts in the host_list

        expected_facts = {**host_list[0].facts[0]["facts"], **facts_to_add}

        target_namespace = host_list[0].facts[0]["namespace"]

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        patch_url = self._build_facts_url(host_list, target_namespace)

        response = self.patch(patch_url, facts_to_add, 200)

        response = self.get(f"{HOST_URL}/{url_host_id_list}", 200)

        self.assertEqual(len(response["results"]), len(host_list))

        for response_host in response["results"]:
            host_to_verify = HostWrapper(response_host)

            self.assertEqual(host_to_verify.facts[0]["facts"],
                             expected_facts)

            self.assertEqual(host_to_verify.facts[0]["namespace"],
                             target_namespace)

    @unittest.skip
    def test_add_facts_to_multiple_hosts_overwrite_empty_key_value_pair(self):
        pass

    @unittest.skip
    def test_add_facts_to_multiple_hosts_overwrite_existing_key_value_pair(self):
        pass

    @unittest.skip
    def test_add_facts_to_multiple_hosts_one_host_does_not_exist(self):
        pass

    @unittest.skip
    def test_add_facts_to_namespace_that_does_not_exist(self):
        pass

    def test_replace_facts_without_fact_dict(self):
        put_url = self._build_facts_url(1, "ns1")
        response = self.put(put_url, None, 400)
        self.assertEqual(response['detail'], "Request body is not valid JSON")

    @unittest.skip
    def test_replace_facts_on_multiple_hosts(self):
        pass

    @unittest.skip
    def test_replace_facts_on_multiple_hosts_one_host_does_not_exist(self):
        pass

    @unittest.skip
    def test_replace_facts_on_namespace_that_does_not_exist(self):
        pass


@bypass_auth
class TagsTestCase(PreCreatedHostsBaseTestCase):

    def _build_tag_op_doc(self, operation, tag):
        return {"operation": operation,
                "tag": tag}

    def test_add_tag_to_host(self):
        tag_to_add = "aws/unique:value"

        tag_op_doc = self._build_tag_op_doc("apply", tag_to_add)

        host_list = self.added_hosts

        expected_tags = host_list[0].tags
        expected_tags.append(tag_to_add)

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        self.post(f"{HOST_URL}/{url_host_id_list}/tags", tag_op_doc, 200)

        response = self.get(f"{HOST_URL}/{url_host_id_list}", 200)

        self.assertEqual(len(response["results"]), len(host_list))

        for response_host in response["results"]:
            host_to_verify = HostWrapper(response_host)

            self.assertListEqual(host_to_verify.tags, expected_tags)

    @unittest.skip
    def test_add_invalid_tag_to_host(self):
        pass

    @unittest.skip
    def test_add_duplicate_tags_to_host(self):
        pass

    def test_remove_tag_from_host(self):
        tag_to_remove = "aws/k:v"

        tag_op_doc = self._build_tag_op_doc("remove", tag_to_remove)

        host_list = self.added_hosts

        expected_tags = host_list[0].tags
        expected_tags.remove(tag_to_remove)

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        self.post(f"{HOST_URL}/{url_host_id_list}/tags", tag_op_doc, 200)

        response = self.get(f"{HOST_URL}/{url_host_id_list}", 200)

        self.assertEqual(len(response["results"]), len(host_list))

        for response_host in response["results"]:
            host_to_verify = HostWrapper(response_host)

            self.assertListEqual(host_to_verify.tags, expected_tags)


class AuthTestCase(BaseAPITestCase):
    @staticmethod
    def _valid_identity():
        """
        Provides a valid Identity object.
        """
        return Identity(account_number="some account number", org_id="some org id")

    @staticmethod
    def _valid_payload():
        """
        Builds a valid HTTP header payload – Base64 encoded JSON string with valid data.
        """
        identity = __class__._valid_identity()
        dict_ = identity._asdict()
        json = dumps(dict_)
        return b64encode(json.encode())

    def _get_hosts(self, headers):
        """
        Issues a GET request to the /hosts URL, providing given headers.
        """
        return self.client().get(HOST_URL, headers=headers)

    def test_validate_missing_identity(self):
        """
        Identity header is not present, 403 Forbidden is returned.
        """
        response = self._get_hosts({})
        self.assertEqual(403, response.status_code)  # Forbidden

    def test_validate_invalid_identity(self):
        """
        Identity header is not valid – empty in this case, 403 Forbidden is returned.
        """
        response = self._get_hosts({"x-rh-identity": ""})
        self.assertEqual(403, response.status_code)  # Forbidden

    def test_validate_valid_identity(self):
        """
        Identity header is valid – non-empty in this case, 200 is returned.
        """
        payload = self._valid_payload()
        response = self._get_hosts({"x-rh-identity": payload})
        self.assertEqual(200, response.status_code)  # OK

    def test_get_identity(self):
        """
        The identity payload is available by the request context = in the views.
        """
        payload = self._valid_payload()
        with self.app.test_request_context(HOST_URL,
                                           method="GET",
                                           headers={"x-rh-identity": payload}):
            self.app.preprocess_request()
            self.assertEquals(self._valid_identity(), current_identity)


if __name__ == "__main__":
    unittest.main()
