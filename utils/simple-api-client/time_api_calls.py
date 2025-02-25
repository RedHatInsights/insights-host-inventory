#!/usr/bin/env python3
import os
import random
import timeit

import simple_hbi_api

num_calls = int(os.getenv("NUM_CALLS", "10"))
repeat = int(os.getenv("TIMEIT_REPEAT", "3"))

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


API_METHODS = (simple_hbi_api.get_hosts,)


def _api_method():
    return random.choice(API_METHODS)


def timed_section():
    _api_method()(headers={"User-Agent": _user_agent()})


dtv = timeit.repeat(timed_section, number=num_calls, repeat=repeat)

print(f"#CALLS: {num_calls}, MIN TIME: {min(dtv)}, VECTOR: {dtv}")
