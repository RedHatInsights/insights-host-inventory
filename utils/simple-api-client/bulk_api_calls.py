#!/usr/bin/env python3
import os
import random

import hbi_api_core
import simple_hbi_api

num_calls = int(os.getenv("NUM_CALLS", "10"))

USER_AGENTS = (
    "insights-client",
    "Mozilla",
    "Chrome",
    "rest-client",
    "Satellite",
    "python-requests/2.31.0",
    "curl/8.1.2",
)


def _user_agent():
    return random.choice(USER_AGENTS)


API_METHODS = (
    simple_hbi_api.get_hosts,
    simple_hbi_api.get_assignment_rules,
)


def _api_method():
    return random.choice(API_METHODS)


for n in range(num_calls):
    api_method = _api_method()
    user_agent = _user_agent()
    print(f"api_method: {api_method.__name__}, User-Agent: {user_agent}")
    resp = api_method(headers={"User-Agent": user_agent})
    hbi_api_core.process_response(resp)
