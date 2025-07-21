#!/usr/bin/env python3
"""
Test script to verify write_event_to_outbox function returns proper boolean values.

Run with: FLASK_APP=manage.py python test_outbox_write.py
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
    """Test that write_event_to_outbox returns True for successful writes."""
    print("Testing successful outbox write...")
    
    # Create a valid event with the expected structure
    host_id = str(uuid.uuid4())
    event_data = {
        "type": "host.created",
        "host": {
            "id": host_id,
            "display_name": "test-host.example.com",
            "reporter": "insights-client",
            "org_id": "test-org-123"
        },
        "payload": {
            "timestamp": datetime.utcnow().isoformat()
        }
    }
    
    # Test with JSON string (the function only accepts strings)
    event_json = json.dumps(event_data)
    result = write_event_to_outbox(event_json)
    assert result == True, f"Expected True, got {result}"
    print("✓ JSON string event write returned True")
    
    # Verify event is in database
    events = Outbox.query.filter(Outbox.aggregate_id == host_id).all()
    assert len(events) >= 1, "Event should be found in database"
    print(f"✓ Found {len(events)} events in database")
    
    # Verify the structure
    event = events[0]
    assert event.type == "host.created"
    assert event.aggregate_type == "hbi.hosts"
    assert str(event.aggregate_id) == host_id
    print("✓ Event structure is correct")
    
    return True


def test_failed_write_missing_fields():
    """Test that write_event_to_outbox returns False for invalid events."""
    print("\nTesting failed outbox write (missing required fields)...")
    
    # Missing required 'type' field
    invalid_event1 = {
        "host": {
            "id": str(uuid.uuid4()),
            "display_name": "missing-type.example.com"
        }
    }
    
    result = write_event_to_outbox(json.dumps(invalid_event1))
    assert result == False, f"Expected False, got {result}"
    print("✓ Missing 'type' field returned False")
    
    # Missing required 'host' field
    invalid_event2 = {
        "type": "host.created",
        "payload": {"test": "data"}
    }
    
    result = write_event_to_outbox(json.dumps(invalid_event2))
    assert result == False, f"Expected False, got {result}"
    print("✓ Missing 'host' field returned False")
    
    # Missing required 'host.id' field
    invalid_event3 = {
        "type": "host.created",
        "host": {
            "display_name": "missing-id.example.com",
            "reporter": "insights-client"
        }
    }
    
    result = write_event_to_outbox(json.dumps(invalid_event3))
    assert result == False, f"Expected False, got {result}"
    print("✓ Missing 'host.id' field returned False")
    
    return True


def test_failed_write_invalid_json():
    """Test that write_event_to_outbox returns False for invalid JSON."""
    print("\nTesting failed outbox write (invalid JSON)...")
    
    # Invalid JSON string
    invalid_json = '{"type": "host.created", "host": {"id": "test"}, invalid}'
    
    result = write_event_to_outbox(invalid_json)
    assert result == False, f"Expected False, got {result}"
    print("✓ Invalid JSON string returned False")
    
    return True


def test_event_with_defaults():
    """Test event creation with default values."""
    print("\nTesting event with default values...")
    
    # Event without custom payload (should use host data as default)
    host_id = str(uuid.uuid4())
    event_data = {
        "type": "host.updated",
        "host": {
            "id": host_id,
            "display_name": "default-payload-host.example.com",
            "reporter": "satellite"
        }
        # No custom payload specified
    }
    
    result = write_event_to_outbox(json.dumps(event_data))
    assert result == True, f"Expected True, got {result}"
    print("✓ Event with defaults returned True")
    
    # Verify event was created with defaults
    event_in_db = Outbox.query.filter(Outbox.aggregate_id == host_id).first()
    assert event_in_db is not None, "Event should be found in database"
    assert event_in_db.aggregate_type == "hbi.hosts", "Should default to hbi.hosts"
    print("✓ Default values applied correctly")
    
    return True


def test_different_event_types():
    """Test different event types."""
    print("\nTesting different event types...")
    
    event_types = ["host.created", "host.updated", "host.deleted", "host.stale"]
    successful_events = 0
    
    for event_type in event_types:
        host_id = str(uuid.uuid4())
        event_data = {
            "type": event_type,
            "host": {
                "id": host_id,
                "display_name": f"test-{event_type.replace('.', '-')}.example.com"
            }
        }
        
        result = write_event_to_outbox(json.dumps(event_data))
        if result:
            successful_events += 1
            print(f"✓ Event type '{event_type}' succeeded")
        else:
            print(f"❌ Event type '{event_type}' failed")
    
    assert successful_events == len(event_types), f"Expected all {len(event_types)} events to succeed, got {successful_events}"
    print(f"✓ All {len(event_types)} event types succeeded")
    
    return True


def cleanup_test_events():
    """Clean up events created during testing."""
    print("\nCleaning up test events...")
    
    # Delete test events
    test_events = Outbox.query.filter(
        Outbox.type.in_(['host.created', 'host.updated', 'host.deleted', 'host.stale'])
    ).all()
    
    for event in test_events:
        db.session.delete(event)
    
    db.session.commit()
    print(f"✓ Cleaned up {len(test_events)} test events")


def main():
    """Main test function."""
    print("=== Testing write_event_to_outbox Boolean Return Values ===")
    print("Expected event structure: JSON string with 'type' and 'host.id' fields")
    
    try:
        # Run all tests
        success1 = test_successful_write()
        success2 = test_failed_write_missing_fields()
        success3 = test_failed_write_invalid_json()
        success4 = test_event_with_defaults()
        success5 = test_different_event_types()
        
        if all([success1, success2, success3, success4, success5]):
            print("\n=== All Tests Passed! ===")
            print("✓ write_event_to_outbox correctly returns True for successful writes")
            print("✓ write_event_to_outbox correctly returns False for failed writes")
            print("✓ Function handles JSON strings with correct structure")
            print("✓ Function applies default values correctly")
            print("✓ Function works with different event types")
            
            # Optional cleanup
            cleanup_test_events()
            
            return True
        else:
            print("\n❌ Some tests failed")
            return False
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Create Flask application context
    app = create_app(RuntimeEnvironment.SERVER)
    
    with app.app_context():
        success = main()
        sys.exit(0 if success else 1) 