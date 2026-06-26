"""
Quality Checks Runner
---------------------
Runs all 5 quality detectors after every pipeline run.
Saves results to Azure SQL.
Opens an incident if any check fails.

How to run:
  python quality/run_checks.py
"""

import os
import sys
import json
import uuid
import urllib
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quality.detectors.freshness    import check_freshness
from quality.detectors.volume       import check_volume
from quality.detectors.null_rate    import check_null_rate
from quality.detectors.schema_drift import check_schema_drift
from quality.detectors.join_rate    import check_join_rate

# ── SQLAlchemy engines (industry standard for pandas) ─────────────
def get_engine():
    params = urllib.parse.quote_plus(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.getenv('SQL_SERVER')};"
        f"DATABASE={os.getenv('SQL_DATABASE', 'pipeline-metadata')};"
        f"UID={os.getenv('SQL_USER', 'sqladmin')};"
        f"PWD={os.getenv('SQL_PASSWORD')};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    return create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

def get_gold_engine():
    params = urllib.parse.quote_plus(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.getenv('SQL_SERVER')};"
        f"DATABASE={os.getenv('SQL_GOLD_DATABASE', 'pipeline-gold')};"
        f"UID={os.getenv('SQL_USER', 'sqladmin')};"
        f"PWD={os.getenv('SQL_PASSWORD')};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    return create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

# ── Helper functions ───────────────────────────────────────────────
def save_result(conn, run_id, result):
    conn.execute(text("""
        INSERT INTO quality_results
            (run_id, table_name, check_name, status,
             observed_value, expected_value, details)
        VALUES (:run_id, :table_name, :check_name, :status,
                :observed, :expected, :details)
    """), {
        "run_id":     run_id,
        "table_name": result.table_name,
        "check_name": result.check,
        "status":     result.status,
        "observed":   result.observed,
        "expected":   result.expected,
        "details":    json.dumps(result.details)
    })

def create_incident(conn, run_id, results):
    failures = [r for r in results if r.status == "fail"]
    if not failures:
        return None

    summary     = f"{len(failures)} check(s) failed: " + \
                  ", ".join([f.check for f in failures])
    severity    = "high" if len(failures) > 2 else "medium"
    incident_id = str(uuid.uuid4())

    conn.execute(text("""
        INSERT INTO incidents
            (incident_id, run_id, severity, summary, status)
        VALUES (:incident_id, :run_id, :severity, :summary, 'open')
    """), {
        "incident_id": incident_id,
        "run_id":      run_id,
        "severity":    severity,
        "summary":     summary
    })

    print(f"\n  🚨 INCIDENT CREATED")
    print(f"  Severity: {severity.upper()}")
    print(f"  Summary:  {summary}")
    print(f"  ID:       {incident_id}")
    return incident_id

def get_latest_run(engine):
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT TOP 1
                CAST(run_id AS NVARCHAR(200)) AS run_id,
                rows_processed,
                pipeline_name,
                CAST(started_at AS DATETIME2) AS started_at
            FROM pipeline_runs
            ORDER BY started_at DESC
        """), conn)
    if df.empty:
        raise Exception("No pipeline runs found. Run ingestion first.")
    return (
        str(df["run_id"].iloc[0]),
        int(df["rows_processed"].iloc[0]),
        str(df["pipeline_name"].iloc[0])
    )

# ── Main ───────────────────────────────────────────────────────────
def run_all_checks():
    print("\n=== Running Data Quality Checks ===")

    engine      = get_engine()
    gold_engine = get_gold_engine()

    # Get latest run
    run_id, row_count, pipeline_name = get_latest_run(engine)
    print(f"\n  Checking run: {pipeline_name} ({row_count} rows)")

    all_results = []

    with engine.connect() as conn:
        with gold_engine.connect() as gold_conn:

            # 1. Freshness
            print("\n  Running freshness check...")
            r = check_freshness("fct_orders", sla_hours=6, conn=gold_conn)
            print(f"  [{r.status.upper()}] Freshness: {r.observed}h old (SLA: {r.expected}h)")
            save_result(conn, run_id, r)
            all_results.append(r)

            # 2. Volume
            print("\n  Running volume check...")
            r = check_volume(pipeline_name, row_count, conn=conn)
            print(f"  [{r.status.upper()}] Volume: {r.observed} rows (expected ~{r.expected})")
            save_result(conn, run_id, r)
            all_results.append(r)

            # 3. Null rates
            print("\n  Running null rate checks...")
            for table, col in [
                ("fct_orders",    "amount"),
                ("fct_orders",    "customer_id"),
                ("dim_customers", "email"),
            ]:
                r = check_null_rate(table, col, conn=gold_conn)
                print(f"  [{r.status.upper()}] Null rate {table}.{col}: "
                      f"{r.details.get('null_pct','?')} "
                      f"(baseline: {r.details.get('baseline_pct','?')})")
                save_result(conn, run_id, r)
                all_results.append(r)

            # 4. Schema drift — check Gold fct_orders
            print("\n  Running schema drift check...")
            r = check_schema_drift("fct_orders", schema_conn=gold_conn, snapshot_conn=conn)
            print(f"  [{r.status.upper()}] Schema drift fct_orders: {r.details}")
            save_result(conn, run_id, r)
            all_results.append(r)

            # 5. Join rate
            print("\n  Running join rate check...")
            r = check_join_rate(conn=gold_conn)
            print(f"  [{r.status.upper()}] Join rate: "
                  f"{r.details.get('join_rate_pct','?')} "
                  f"(baseline: {r.details.get('baseline_pct','?')})")
            save_result(conn, run_id, r)
            all_results.append(r)

            # Open incident if anything failed
            incident_id = create_incident(conn, run_id, all_results)
            conn.commit()

    # Summary
    passes = sum(1 for r in all_results if r.status == "pass")
    warns  = sum(1 for r in all_results if r.status == "warn")
    fails  = sum(1 for r in all_results if r.status == "fail")
    print(f"\n=== Results: {passes} pass | {warns} warn | {fails} fail ===")

    return incident_id

if __name__ == "__main__":
    incident_id = run_all_checks()
    if incident_id:
        print(f"\n  Next step: python -m rca.analyzer --incident {incident_id}")