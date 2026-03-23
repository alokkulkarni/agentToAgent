"""
Database schema migration script
"""
import sqlite3
import os

def migrate_database():
    """Add missing columns to existing database"""
    db_path = "workflows.db"
    
    if not os.path.exists(db_path):
        print("No existing database found - will be created with new schema")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if current_step column exists
    cursor.execute("PRAGMA table_info(workflows)")
    columns = [row[1] for row in cursor.fetchall()]
    
    migrations_applied = []
    
    if 'current_step' not in columns:
        print("Adding current_step column...")
        cursor.execute("ALTER TABLE workflows ADD COLUMN current_step INTEGER DEFAULT 0")
        migrations_applied.append("current_step")
    
    if 'workflow_state' not in columns:
        print("Adding workflow_state column...")
        cursor.execute("ALTER TABLE workflows ADD COLUMN workflow_state TEXT")
        migrations_applied.append("workflow_state")
    
    if migrations_applied:
        conn.commit()
        print(f"\n✅ Applied migrations: {', '.join(migrations_applied)}")
    else:
        print("✅ Database schema is up to date")
    
    conn.close()

if __name__ == "__main__":
    migrate_database()
