"""
CivicMind — Database Interface
==============================
Local fallback: SQLite
Google Cloud swap-in: Replace SqliteDatabase with a BigQueryDatabase class
that uses the google-cloud-bigquery client. The interface (execute_query,
get_table_schema, list_tables) stays identical.
"""

import sqlite3
import os
from pathlib import Path
from typing import Any


DB_PATH = Path(__file__).parent.parent.parent / "data" / "structured" / "civic_records.db"


class DatabaseInterface:
    """Abstract interface for structured data queries.

    Google Cloud swap-in:
        Replace this with a BigQueryDatabase that wraps google.cloud.bigquery.Client.
        Methods to implement:
        - execute_query(sql) -> list[dict]
        - get_table_schema(table_name) -> list[dict]
        - list_tables() -> list[str]
    """

    def execute_query(self, sql: str) -> list[dict]:
        raise NotImplementedError

    def get_table_schema(self, table_name: str) -> list[dict]:
        raise NotImplementedError

    def list_tables(self) -> list[str]:
        raise NotImplementedError


class SqliteDatabase(DatabaseInterface):
    """Local SQLite implementation of the database interface."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(DB_PATH)
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(
                f"Database not found at {self.db_path}. Run 'python data/seed.py' first."
            )

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def execute_query(self, sql: str) -> list[dict]:
        """Execute a SQL query and return results as list of dicts.

        Raises ValueError on SQL errors (caught gracefully by the stream handler).
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        except sqlite3.Error as e:
            raise ValueError(f"SQL execution error: {e}")
        finally:
            conn.close()

    def get_table_schema(self, table_name: str) -> list[dict]:
        """Get column info for a table."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            return [
                {"name": row[1], "type": row[2], "nullable": not row[3]}
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def list_tables(self) -> list[str]:
        """List all tables in the database."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_schema_description(self) -> str:
        """Get a human-readable schema description for NL-to-SQL prompting."""
        tables = self.list_tables()
        parts = []
        for table in tables:
            schema = self.get_table_schema(table)
            cols = ", ".join([f"{c['name']} ({c['type']})" for c in schema])
            parts.append(f"Table: {table}\n  Columns: {cols}")

            # Get sample data
            try:
                sample = self.execute_query(f"SELECT * FROM {table} LIMIT 3")
                if sample:
                    parts.append(f"  Sample row: {sample[0]}")
            except Exception:
                pass

        return "\n\n".join(parts)


# Singleton
_db_instance = None

def get_database() -> SqliteDatabase:
    global _db_instance
    if _db_instance is None:
        _db_instance = SqliteDatabase()
    return _db_instance
