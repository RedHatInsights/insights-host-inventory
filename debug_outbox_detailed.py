#!/usr/bin/env python3
"""
Comprehensive debug script for write_event_to_outbox function
"""

import json
import uuid
import sys
import os
import logging

# Set up basic logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(name)s - %(message)s')

# Set up environment
os.environ['FLASK_APP'] = 'manage.py'

def test_json_parsing():
    """Test basic JSON parsing functionality"""
    print("=== Testing JSON Parsing ===")
    
    host_id = str(uuid.uuid4())
    event_data = {
        "type": "host.created",
        "host": {
            "id": host_id,
            "display_name": "test-host.example.com"
        }
    }
    
    try:
        event_json = json.dumps(event_data)
        print(f"✓ JSON creation successful: {len(event_json)} chars")
        
        parsed = json.loads(event_json)
        print(f"✓ JSON parsing successful")
        
        # Test field access
        assert parsed["type"] == "host.created"
        assert parsed["host"]["id"] == host_id
        print("✓ Field access successful")
        
        return True
    except Exception as e:
        print(f"❌ JSON test failed: {e}")
        return False


def test_imports():
    """Test importing the required modules"""
    print("\n=== Testing Imports ===")
    
    try:
        # Test basic imports
        from lib.outbox_repository import write_event_to_outbox
        print("✓ Successfully imported write_event_to_outbox")
        
        # Test model imports  
        from app.models import Outbox, db
        print("✓ Successfully imported Outbox and db")
        
        # Test app creation
        from app import create_app
        from app.environment import RuntimeEnvironment
        print("✓ Successfully imported Flask components")
        
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Other error during import: {e}")
        return False


def test_flask_app_creation():
    """Test creating Flask application"""
    print("\n=== Testing Flask App Creation ===")
    
    try:
        from app import create_app
        from app.environment import RuntimeEnvironment
        
        app = create_app(RuntimeEnvironment.SERVER)
        print("✓ Flask app created successfully")
        
        # Test app context
        with app.app_context():
            print("✓ Flask app context created successfully")
            
            # Test database access
            from app.models import db
            print(f"✓ Database object accessible: {db}")
            
            return app
    except Exception as e:
        print(f"❌ Flask app creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_database_operations(app):
    """Test basic database operations"""
    print("\n=== Testing Database Operations ===")
    
    if not app:
        print("❌ No Flask app available for database testing")
        return False
    
    try:
        with app.app_context():
            from app.models import Outbox, db
            
            # Test basic database connection
            print("Testing database connection...")
            
            # Try to create tables
            try:
                db.create_all()
                print("✓ Database tables created/verified")
            except Exception as e:
                print(f"⚠️  Database table creation issue: {e}")
            
            # Test creating an Outbox object
            test_outbox = Outbox(
                aggregate_id=str(uuid.uuid4()),
                type="test.event",
                payload={"test": "data"}
            )
            print("✓ Outbox object created successfully")
            
            # Test adding to session (without committing)
            db.session.add(test_outbox)
            print("✓ Object added to session")
            
            # Test rolling back
            db.session.rollback()
            print("✓ Session rollback successful")
            
            return True
    except Exception as e:
        print(f"❌ Database operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_outbox_function(app):
    """Test the actual write_event_to_outbox function"""
    print("\n=== Testing write_event_to_outbox Function ===")
    
    if not app:
        print("❌ No Flask app available for function testing")
        return False
    
    try:
        from lib.outbox_repository import write_event_to_outbox
        
        with app.app_context():
            # Create test event
            host_id = str(uuid.uuid4())
            event_data = {
                "type": "host.created",
                "host": {
                    "id": host_id,
                    "display_name": "function-test.example.com"
                }
            }
            event_json = json.dumps(event_data)
            
            print(f"Test event: {event_json}")
            
            # Call the function
            print("Calling write_event_to_outbox...")
            result = write_event_to_outbox(event_json)
            
            print(f"Function result: {result}")
            
            if result:
                print("✓ Function returned True")
                
                # Try to query the database
                from app.models import Outbox
                try:
                    entry = Outbox.query.filter(Outbox.aggregate_id == host_id).first()
                    if entry:
                        print(f"✓ Event found in database: {entry.id}")
                        print(f"  Type: {entry.type}")
                        print(f"  Aggregate ID: {entry.aggregate_id}")
                        return True
                    else:
                        print("❌ Event not found in database (but function returned True)")
                        return False
                except Exception as e:
                    print(f"❌ Database query failed: {e}")
                    return False
            else:
                print("❌ Function returned False")
                return False
                
    except Exception as e:
        print(f"❌ Function test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run comprehensive debugging"""
    print("🔍 Comprehensive Outbox Function Debug")
    print("=" * 50)
    
    # Test 1: JSON parsing
    json_ok = test_json_parsing()
    
    # Test 2: Imports
    imports_ok = test_imports()
    
    if not imports_ok:
        print("\n❌ Cannot proceed without successful imports")
        return False
    
    # Test 3: Flask app creation
    app = test_flask_app_creation()
    
    # Test 4: Database operations
    db_ok = test_database_operations(app)
    
    # Test 5: Outbox function
    function_ok = test_outbox_function(app)
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 DEBUGGING SUMMARY:")
    print(f"JSON Parsing: {'✅ PASS' if json_ok else '❌ FAIL'}")
    print(f"Imports: {'✅ PASS' if imports_ok else '❌ FAIL'}")
    print(f"Flask App: {'✅ PASS' if app else '❌ FAIL'}")
    print(f"Database Ops: {'✅ PASS' if db_ok else '❌ FAIL'}")
    print(f"Outbox Function: {'✅ PASS' if function_ok else '❌ FAIL'}")
    
    if all([json_ok, imports_ok, app, db_ok, function_ok]):
        print("\n🎉 All tests passed! The function should work correctly.")
    else:
        print("\n❌ Some tests failed. The function may not work in the test environment.")
        print("\nThis explains why the pytest tests are failing.")
    
    return all([json_ok, imports_ok, app, db_ok, function_ok])


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 