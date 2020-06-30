import os
import sys

# Make test helpers available to be imported
sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))

# Make fixtures available
pytest_plugins = [
    "tests.fixtures.api_fixtures",
    "tests.fixtures.app_fixtures",
    "tests.fixtures.db_fixtures",
    "tests.fixtures.graphql_fixtures",
    "tests.fixtures.mq_fixtures",
    "tests.fixtures.tracker_fixtures",
]
