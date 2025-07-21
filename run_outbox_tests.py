#!/usr/bin/env python3
"""
Simple test runner for write_event_to_outbox function.

This script can be run directly to test the outbox functionality without pytest.
Run with: FLASK_APP=manage.py python run_outbox_tests.py
"""

import json
import uuid
import sys
from datetime import datetime

from app import create_app
from app.environment import RuntimeEnvironment
from lib.outbox_repository import write_event_to_outbox
from app.models import Outbox, db


def test_successful_write():
    """Test successful event write."""
    print("Testing successful write...")

    host_id = str(uuid.uuid4())
    event_json = json.dumps({
        "type": "host.created",
        "host": {
            "id": host_id,
            "display_name": "test-host.example.com",
            "reporter": "insights-client",
            "org_id": "test-org-123"
        }
    })

# sourcery skip: no-conditionals-in-tests
    if write_event_to_outbox(event_json):
        print("✓ Event write returned True")

        if outbox_entry := Outbox.query.filter(
            Outbox.aggregate_id == host_id
        ).first():
            print(f"✓ Event found in database: {outbox_entry.id}")
            print(f"  Type: {outbox_entry.type}")
            print(f"  Aggregate Type: {outbox_entry.aggregate_type}")
            print(f"  Aggregate ID: {outbox_entry.aggregate_id}")
            return True
        else:
            print("❌ Event not found in database")
            return False
    else:
        print("❌ Event write returned False")
        return False


def test_custom_payload():
    """Test event with custom payload."""
    print("\nTesting custom payload...")

    host_id = str(uuid.uuid4())
    custom_payload = {
        "custom_field": "custom_value",
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": {"source": "test"}
    }

    event_json = json.dumps({
        "type": "host.updated",
        "host": {
            "id": host_id,
            "display_name": "custom-payload-host.example.com"
        },
        "payload": custom_payload
    })

    if result := write_event_to_outbox(event_json):
        print("✓ Custom payload event write returned True")

        # Verify payload in database
        outbox_entry = Outbox.query.filter(Outbox.aggregate_id == host_id).first()
        if outbox_entry and outbox_entry.payload == custom_payload:
            print("✓ Custom payload correctly stored")
            return True
        else:
            print("❌ Custom payload not correctly stored")
            print(f"Expected: {custom_payload}")
            print(f"Got: {outbox_entry.payload if outbox_entry else 'No entry'}")
            return False
    else:
        print("❌ Custom payload event write returned False")
        return False


def test_default_payload():
    """Test event with default payload (no payload specified)."""
    print("\nTesting default payload...")

    host_id = str(uuid.uuid4())
    host_data = {
        "id": host_id,
        "display_name": "default-payload-host.example.com",
        "reporter": "satellite"
    }

    event_json = json.dumps({
        "type": "host.deleted",
        "host": host_data
    })

# sourcery skip: no-conditionals-in-tests
    if result := write_event_to_outbox(event_json):
        print("✓ Default payload event write returned True")

        if outbox_entry := Outbox.query.filter(
            Outbox.aggregate_id == host_id
        ).first():
            print(f"✓ Default payload stored: {outbox_entry.payload}")
            return True
        else:
            print("❌ Event not found in database")
            return False
    else:
        print("❌ Default payload event write returned False")
        return False


def test_missing_required_fields():
    """Test events with missing required fields."""
    print("\nTesting missing required fields...")
    
    # Test missing 'type' field
    event_json1 = json.dumps({
        "host": {
            "id": str(uuid.uuid4()),
            "display_name": "missing-type.example.com"
        }
    })
    
    result1 = write_event_to_outbox(event_json1)
    if not result1:
        print("✓ Missing 'type' field correctly returned False")
    else:
        print("❌ Missing 'type' field should have returned False")
        return False
    
    # Test missing 'host' field
    event_json2 = json.dumps({
        "type": "host.created",
        "some_other_field": "value"
    })
    
    result2 = write_event_to_outbox(event_json2)
    if not result2:
        print("✓ Missing 'host' field correctly returned False")
    else:
        print("❌ Missing 'host' field should have returned False")
        return False
    
    # Test missing 'host.id' field
    event_json3 = json.dumps({
        "type": "host.created",
        "host": {
            "display_name": "missing-id.example.com",
            "reporter": "insights-client"
        }
    })
    
    result3 = write_event_to_outbox(event_json3)
    if not result3:
        print("✓ Missing 'host.id' field correctly returned False")
        return True
    else:
        print("❌ Missing 'host.id' field should have returned False")
        return False


def test_invalid_json():
    """Test invalid JSON input."""
    print("\nTesting invalid JSON...")
    
    invalid_json = '{"type": "host.created", "host": {"id": "test"}, invalid}'
    
    result = write_event_to_outbox(invalid_json)
    
    if not result:
        print("✓ Invalid JSON correctly returned False")
        return True
    else:
        print("❌ Invalid JSON should have returned False")
        return False


def test_different_event_types():
    """Test different event types."""
    print("\nTesting different event types...")
    
    event_types = [
        "host.created",
        "host.updated", 
        "host.deleted",
        "host.stale",
        "host.culled"
    ]
    
    success_count = 0
    
    for event_type in event_types:
        host_id = str(uuid.uuid4())
        event_json = json.dumps({
            "type": event_type,
            "host": {
                "id": host_id,
                "display_name": f"test-{event_type.replace('.', '-')}.example.com"
            }
        })
        
        result = write_event_to_outbox(event_json)
        if result:
            print(f"✓ Event type '{event_type}' succeeded")
            success_count += 1
        else:
            print(f"❌ Event type '{event_type}' failed")
    
    if success_count == len(event_types):
        print(f"✓ All {len(event_types)} event types succeeded")
        return True
    else:
        print(f"❌ Only {success_count}/{len(event_types)} event types succeeded")
        return False


def cleanup_test_events():
    """Clean up test events."""
    print("\nCleaning up test events...")
    
    # Delete test events
    test_events = Outbox.query.filter(
        Outbox.type.in_(['host.created', 'host.updated', 'host.deleted', 'host.stale', 'host.culled'])
    ).all()
    
    for event in test_events:
        db.session.delete(event)
    
    db.session.commit()
    print(f"✓ Cleaned up {len(test_events)} test events")


def main():
    """Run all tests."""
    print("=== Testing write_event_to_outbox Function ===")
    print(f"Expected event structure: JSON string with 'type' and 'host.id' fields")
    
    tests = [
        test_successful_write,
        test_custom_payload,
        test_default_payload,
        test_missing_required_fields,
        test_invalid_json,
        test_different_event_types
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test_func.__name__} failed with exception: {e}")
            failed += 1
    
    print(f"\n=== Test Results ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total: {passed + failed}")
    
    if failed == 0:
        print("🎉 All tests passed!")
        success = True
    else:
        print("❌ Some tests failed!")
        success = False
    
    # Clean up
    try:
        cleanup_test_events()
    except Exception as e:
        print(f"Warning: Failed to clean up test events: {e}")
    
    return success


if __name__ == "__main__":
    # Create Flask application context
    app = create_app(RuntimeEnvironment.SERVER)
    
    with app.app.app_context():
        success = main()
        sys.exit(0 if success else 1) 