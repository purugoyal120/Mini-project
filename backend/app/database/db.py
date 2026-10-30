"""
SQLite Database connection and table setup for APIBridge AI.
Beginner-friendly implementation using Python's standard sqlite3 module.
"""

import sqlite3
import os
from pathlib import Path

# Path to the SQLite database file
DB_DIR = Path(__file__).resolve().parent.parent.parent / "database"
DB_PATH = DB_DIR / "apibridge.db"

# Pytest test isolation: use separate test database during automated test execution
TEST_DB_PATH = DB_DIR / "test_apibridge.db"


def get_db():
    """
    Creates and returns a connection to the SQLite database.
    Row factory is set to sqlite3.Row so query results behave like Python dictionaries.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    active_path = TEST_DB_PATH if "PYTEST_CURRENT_TEST" in os.environ else DB_PATH
    conn = sqlite3.connect(active_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """
    Initializes the database by creating all necessary tables if they do not exist.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Table 1: Registered APIs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS apis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Table 2: Versioned OpenAPI/Swagger specifications
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS spec_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_id INTEGER NOT NULL,
        version_tag TEXT NOT NULL,
        raw_spec TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (api_id) REFERENCES apis(id) ON DELETE CASCADE,
        UNIQUE(api_id, version_tag)
    );
    """)

    # Table 3: Detected changes between two API versions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_id INTEGER NOT NULL,
        old_version_id INTEGER NOT NULL,
        new_version_id INTEGER NOT NULL,
        endpoint TEXT NOT NULL,
        method TEXT NOT NULL,
        change_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT NOT NULL,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (api_id) REFERENCES apis(id) ON DELETE CASCADE
    );
    """)

    # Ensure details column exists if table was created in older schema
    try:
        cursor.execute("ALTER TABLE changes ADD COLUMN details TEXT")
    except Exception:
        pass

    # Table 4: Generated adapters for breaking changes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS adapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_id INTEGER NOT NULL,
        old_endpoint TEXT NOT NULL,
        new_endpoint TEXT NOT NULL,
        method TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        adapter_code TEXT NOT NULL,
        explanation TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (api_id) REFERENCES apis(id) ON DELETE CASCADE
    );
    """)

    # Table 5: Test execution records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS test_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        adapter_id INTEGER,
        test_name TEXT NOT NULL,
        status TEXT NOT NULL,
        details TEXT,
        executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (adapter_id) REFERENCES adapters(id) ON DELETE SET NULL
    );
    """)

    conn.commit()
    conn.close()
