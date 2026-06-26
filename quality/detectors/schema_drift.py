"""
Schema Drift Detector
---------------------
Compares the current table schema to the last known snapshot.
Detects when columns are added, removed, or change type.

What it does:
- Gets current columns and types from INFORMATION_SCHEMA
- Gets last known columns from schema_snapshots table
- Compares the two sets
- Fails if columns were REMOVED or TYPES CHANGED (breaking changes)
- Warns if columns were ADDED (non-breaking change)

Why it matters:
- Source systems change schemas without telling anyone
- A removed column breaks downstream pipelines silently
- Example: Customer API adds loyalty_tier column
  → schema drift detector catches it immediately

First run behaviour:
- No snapshot exists yet → saves current schema as baseline → pass
"""

from sqlalchemy import text
import pandas as pd
from .base import CheckResult

def get_current_schema(table: str, conn) -> dict:
    df = pd.read_sql(text(f"""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = '{table}'
        ORDER BY ORDINAL_POSITION
    """), conn)
    return dict(zip(df["COLUMN_NAME"], df["DATA_TYPE"]))

def get_stored_schema(table: str, conn) -> dict:
    df = pd.read_sql(text(f"""
        SELECT column_name, data_type
        FROM schema_snapshots
        WHERE table_name = '{table}'
          AND captured_at = (
              SELECT MAX(captured_at)
              FROM schema_snapshots
              WHERE table_name = '{table}'
          )
    """), conn)
    if df.empty:
        return None
    return dict(zip(df["column_name"], df["data_type"]))

def save_schema_snapshot(table: str, schema: dict, conn):
    for col, dtype in schema.items():
        conn.execute(text("""
            INSERT INTO schema_snapshots (table_name, column_name, data_type)
            VALUES (:table, :col, :dtype)
        """), {"table": table, "col": col, "dtype": dtype})

def check_schema_drift(table: str, schema_conn, snapshot_conn) -> CheckResult:
    try:
        current    = get_current_schema(table, schema_conn)
        last_known = get_stored_schema(table, snapshot_conn)

        if last_known is None:
            save_schema_snapshot(table, current, snapshot_conn)
            return CheckResult(
                check="schema_drift", table_name=table,
                status="pass", observed=0, expected=0,
                details={"message": "First run — baseline saved", "columns": list(current.keys())}
            )

        added        = set(current)    - set(last_known)
        removed      = set(last_known) - set(current)
        type_changes = {c for c in current if c in last_known and current[c] != last_known[c]}

        if removed or type_changes:
            status = "fail"
        elif added:
            status = "warn"
            save_schema_snapshot(table, current, snapshot_conn)
        else:
            status = "pass"
            save_schema_snapshot(table, current, snapshot_conn)

        return CheckResult(
            check="schema_drift", table_name=table,
            status=status,
            observed=1.0 if status != "pass" else 0.0,
            expected=0.0,
            details={
                "added_columns":   list(added),
                "removed_columns": list(removed),
                "type_changes":    list(type_changes)
            }
        )

    except Exception as e:
        return CheckResult(
            check="schema_drift", table_name=table,
            status="fail", observed=-1, expected=0,
            details={"error": str(e)}
        )