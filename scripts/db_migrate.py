#!/usr/bin/env python3
"""Apply database migrations."""
import os
import psycopg2
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).parent.parent / "src" / "database"


def get_connection(conn_string=None):
    """Get database connection."""
    if conn_string is None:
        conn_string = os.getenv(
            "DATABASE_URL",
            "postgresql://mcphub:mcphub_password@localhost:5432/mcphub",
        )
    return psycopg2.connect(conn_string)


def apply_schema():
    """Apply the base schema."""
    schema_file = MIGRATIONS_DIR / "schema.sql"
    if not schema_file.exists():
        print(f"Schema file not found: {schema_file}")
        return False

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(schema_file.read_text())
        conn.commit()
        print("Schema applied successfully.")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error applying schema: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    apply_schema()
