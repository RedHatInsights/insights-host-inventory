#!/usr/bin/env python3
"""
Simple debug script to test outbox function logic without database
"""

import json
import uuid


def mock_write_event_to_outbox(event: str) -> bool:
    """
    Mock version that mimics the logic of write_event_to_outbox without database operations
    """
    try:
        # Convert event to dictionary from string
        event_dict = json.loads(event) if isinstance(event, str) else event
        print(f"Parsed event: {event_dict}")
        
        # Check required fields (same logic as real function)
        aggregate_id = event_dict["host"]["id"]
        event_type = event_dict["type"]
        payload = event_dict.get("payload", event_dict["host"])
        
        print(f"Aggregate ID: {aggregate_id}")
        print(f"Event Type: {event_type}")
        print(f"Payload: {payload}")
        
        # If we get here, all required fields are present
        print("✓ All required fields present")
        return True

    except KeyError as e:
        print(f"❌ Missing required field: {e}")
        return False

    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        return False

    except Exception as e:
        print(f"❌ Other error: {e}")
        return False


def test_valid_events():
    """Test valid event structures"""
    print("=== Testing Valid Events ===")
    
    # Test 1: Basic valid event
    host_id = str(uuid.uuid4())
    event1 = json.dumps({
        "type": "host.created",
        "host": {
            "id": host_id,
            "display_name": "test-host.example.com"
        }
    })
    
    print("\n--- Test 1: Basic valid event ---")
    result1 = mock_write_event_to_outbox(event1)
    print(f"Result: {result1} (should be True)")
    
    # Test 2: Event with custom payload
    event2 = json.dumps({
        "type": "host.updated",
        "host": {
            "id": str(uuid.uuid4()),
            "display_name": "updated-host.example.com"
        },
        "payload": {
            "custom_field": "custom_value"
        }
    })
    
    print("\n--- Test 2: Event with custom payload ---")
    result2 = mock_write_event_to_outbox(event2)
    print(f"Result: {result2} (should be True)")
    
    return result1 and result2


def test_invalid_events():
    """Test invalid event structures"""
    print("\n=== Testing Invalid Events ===")
    
    # Test 1: Missing type field
    event1 = json.dumps({
        "host": {
            "id": str(uuid.uuid4()),
            "display_name": "missing-type.example.com"
        }
    })
    
    print("\n--- Test 1: Missing type field ---")
    result1 = mock_write_event_to_outbox(event1)
    print(f"Result: {result1} (should be False)")
    
    # Test 2: Missing host field
    event2 = json.dumps({
        "type": "host.created"
    })
    
    print("\n--- Test 2: Missing host field ---")
    result2 = mock_write_event_to_outbox(event2)
    print(f"Result: {result2} (should be False)")
    
    # Test 3: Missing host.id field
    event3 = json.dumps({
        "type": "host.created",
        "host": {
            "display_name": "missing-id.example.com"
        }
    })
    
    print("\n--- Test 3: Missing host.id field ---")
    result3 = mock_write_event_to_outbox(event3)
    print(f"Result: {result3} (should be False)")
    
    return (not result1) and (not result2) and (not result3)


def main():
    """Run tests"""
    print("🧪 Testing Outbox Function Logic")
    print("=" * 40)
    
    valid_tests_passed = test_valid_events()
    invalid_tests_passed = test_invalid_events()
    
    print("\n" + "=" * 40)
    print("📋 SUMMARY:")
    print(f"Valid events test: {'✅ PASSED' if valid_tests_passed else '❌ FAILED'}")
    print(f"Invalid events test: {'✅ PASSED' if invalid_tests_passed else '❌ FAILED'}")
    
    if valid_tests_passed and invalid_tests_passed:
        print("🎉 All logic tests passed!")
        print("\nThe issue is likely with database connectivity or Flask app context in the real tests.")
    else:
        print("❌ Logic tests failed - there's an issue with the function implementation")
    
    return valid_tests_passed and invalid_tests_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 