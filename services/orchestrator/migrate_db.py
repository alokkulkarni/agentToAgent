#!/usr/bin/env python3
"""
Migrate database schema to add missing tables
"""
import sqlite3
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from database import WorkflowDatabase

def check_and_migrate():
    """Check database schema and migrate if needed"""
    db_path = "workflows.db"
    
    print(f"Checking database: {db_path}")
    
    # Check if interaction_requests table exists
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='interaction_requests'
    """)
    
    has_interaction_table = cursor.fetchone() is not None
    conn.close()
    
    if has_interaction_table:
        print("✅ Database schema is up to date")
        return True
    
    print("❌ Missing interaction_requests table")
    print("🔧 Running migration...")
    
    # Re-initialize database to add missing tables
    db = WorkflowDatabase(db_path)
    
    print("✅ Migration complete")
    
    # Verify
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table'
        ORDER BY name
    """)
    
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    print(f"\nAvailable tables:")
    for table in tables:
        print(f"  - {table}")
    
    return True

if __name__ == "__main__":
    try:
        check_and_migrate()
        sys.exit(0)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
