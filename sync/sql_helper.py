"""
SQL Helper - Database connection management for SyncService
Handles SAP SQL Anywhere database connections
"""
import os
import json
from pathlib import Path

# Try to import sqlanydb, but don't fail if it's not available
try:
    import sqlanydb
    SQLANYDB_AVAILABLE = True
except ImportError:
    SQLANYDB_AVAILABLE = False
    print("WARNING: sqlanydb module not found. Database connections will not work.")
    print("Install SAP SQL Anywhere client and run: pip install sqlanydb")

def _get_config():
    """Load configuration from config.json"""
    try:
        # Look for config.json in parent directories
        current_dir = Path(__file__).parent
        config_paths = [
            current_dir / "config.json",
            current_dir.parent / "config.json",
            current_dir.parent.parent / "config.json",
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return json.load(f)
        
        # Return defaults if no config found
        return {
            "dsn": "pktc",
            "db_uid": "dba",
            "db_pwd": "sql"
        }
    except Exception as e:
        print(f"Error loading config: {e}")
        return {
            "dsn": "pktc",
            "db_uid": "dba",
            "db_pwd": "sql"
        }

def get_connection():
    """
    Get a database connection to SAP SQL Anywhere
    Returns a sqlanydb connection object
    """
    if not SQLANYDB_AVAILABLE:
        raise ImportError(
            "sqlanydb module not installed. "
            "Install SAP SQL Anywhere client and run: pip install sqlanydb"
        )
    
    config = _get_config()
    
    # Get credentials from environment variables or config
    dsn = os.getenv("DB_DSN", config.get("dsn", "pktc"))
    uid = os.getenv("DB_UID", config.get("db_uid", "dba"))
    pwd = os.getenv("DB_PWD", config.get("db_pwd", "sql"))
    
    try:
        conn = sqlanydb.connect(
            DSN=dsn,
            UID=uid,
            PWD=pwd
        )
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        print(f"DSN: {dsn}, UID: {uid}")
        raise

def test_connection():
    """Test database connectivity"""
    if not SQLANYDB_AVAILABLE:
        print("Cannot test connection - sqlanydb module not available")
        return False
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        cur.close()
        conn.close()
        print("Database connection successful!")
        return True
    except Exception as e:
        print(f"Database connection test failed: {e}")
        return False

if __name__ == "__main__":
    # Test the connection when run directly
    test_connection()