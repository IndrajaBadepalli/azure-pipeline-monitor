"""
Context Builder
---------------
Assembles everything the LLM needs to diagnose an incident.
"""

import os
import json
import urllib
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

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

def get_connection():
    return get_engine().connect()

def build_context(incident_id: str) -> dict:
    engine = get_engine()

    with engine.connect() as conn:
        # Get the incident
        incident_df = pd.read_sql(text(f"""
            SELECT
                CAST(incident_id AS NVARCHAR(200)) AS incident_id,
                CAST(run_id AS NVARCHAR(200))      AS run_id,
                severity, summary, status
            FROM incidents
            WHERE CAST(incident_id AS NVARCHAR(200)) = '{incident_id}'
        """), conn)

        if incident_df.empty:
            raise ValueError(f"Incident {incident_id} not found")

        incident = incident_df.iloc[0].to_dict()
        run_id   = incident["run_id"]

        # Get failing quality checks
        checks_df = pd.read_sql(text(f"""
            SELECT
                check_name, table_name, status,
                observed_value, expected_value, details
            FROM quality_results
            WHERE CAST(run_id AS NVARCHAR(200)) = '{run_id}'
              AND status IN ('fail', 'warn')
        """), conn)
        failing_checks = checks_df.to_dict(orient="records")

        # Get last 10 pipeline runs
        history_df = pd.read_sql(text("""
            SELECT TOP 10
                pipeline_name, status, rows_processed,
                CAST(started_at AS DATETIME2) AS started_at
            FROM pipeline_runs
            ORDER BY started_at DESC
        """), conn)
        run_history = history_df.to_dict(orient="records")

        # Get schema diff if available
        schema_check = checks_df[checks_df["check_name"] == "schema_drift"]
        schema_diff  = {}
        if not schema_check.empty:
            try:
                schema_diff = json.loads(
                    schema_check.iloc[0]["details"].replace("'", '"')
                )
            except Exception:
                schema_diff = {"raw": schema_check.iloc[0]["details"]}

    return {
        "incident_id":      incident_id,
        "incident_summary": incident["summary"],
        "severity":         incident["severity"],
        "failing_checks":   failing_checks,
        "run_history":      run_history,
        "schema_diff":      schema_diff,
    }