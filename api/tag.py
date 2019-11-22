from api import api_operation
from api import metrics


@api_operation
@metrics.api_request_time.time()
def get_tags():
    return {
        "results": [
            {"count": 3, "tag": {"key": "env", "namespace": "Sat", "value": "prod"}},
            {"count": 1, "tag": {"key": "region", "namespace": "aws", "value": "us-east-1"}},
            {"count": -1, "tag": {"key": "web", "namespace": "insights-client", "value": None}},
        ]
    }
