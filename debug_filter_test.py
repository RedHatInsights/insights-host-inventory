#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

# Test the filtering logic directly
from api.filtering.db_custom_filters import build_single_filter

# Test with placeholder value
filter_param = {"insights_client_version": "app__ENCODED_ASTERISK_PLACEHOLDER__config.json"}
print(f"Filter param: {filter_param}")

try:
    # This would normally create a SQLAlchemy filter expression
    result = build_single_filter(filter_param)
    print(f"Filter result: {result}")
    print(f"Filter result type: {type(result)}")
    print(f"Filter result str: {str(result)}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
