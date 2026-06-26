"""
Customer Ingestion Script
-------------------------
What it does:
  1. Pages through the Customer API for all customer profiles
  2. Fetches all customer behavioural events
  3. Fetches segment definitions
  4. Uploads all three as Parquet to ADLS Bronze
  5. Records the run in Azure SQL

How to run:
  python ingestion/adf_ingest_customers.py
  python ingestion/adf_ingest_customers.py --failure null_spike
  python ingestion/adf_ingest_customers.py --failure schema_change
  python ingestion/adf_ingest_customers.py --failure volume_drop
"""

import os
import io
import argparse
import requests
import pandas as pd
import pyodbc
from datetime import datetime
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

def get_blob_client() -> BlobServiceClient:
    return BlobServiceClient(
        account_url=f"https://{os.getenv('ADLS_ACCOUNT_NAME')}.blob.core.windows.net",
        credential=os.getenv('ADLS_ACCOUNT_KEY')
    )

def get_sql_connection():
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.getenv('SQL_SERVER')};"
        f"DATABASE={os.getenv('SQL_DATABASE', 'pipeline-metadata')};"
        f"UID={os.getenv('SQL_USER', 'sqladmin')};"
        f"PWD={os.getenv('SQL_PASSWORD')};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )

def fetch_all_pages(endpoint: str, page_size: int = 100,
                    failure: str = None) -> list:
    api_url     = os.getenv("CUSTOMER_API_URL", "http://localhost:8001")
    all_records = []
    page        = 1

    while True:
        params = {"page": page, "page_size": page_size}
        if failure:
            params["failure"] = failure

        print(f"  Fetching {endpoint} page {page}...")
        resp = requests.get(f"{api_url}/{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        all_records.extend(data["data"])

        if len(all_records) >= data["total"]:
            break
        page += 1

    print(f"  Total {endpoint}: {len(all_records)} records")
    return all_records

def fetch_segments() -> list:
    api_url = os.getenv("CUSTOMER_API_URL", "http://localhost:8001")
    resp    = requests.get(f"{api_url}/segments", timeout=15)
    resp.raise_for_status()
    return resp.json()["data"]

def upload_to_bronze(blob_client, data: list,
                     entity_name: str, subfolder: str = None) -> int:
    df = pd.DataFrame(data)
    df["ingested_at"]  = datetime.utcnow().isoformat()
    df["adf_pipeline"] = "pl_ingest_customers"

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    today     = datetime.utcnow().strftime("%Y/%m/%d")
    folder    = subfolder or entity_name
    blob_path = f"{folder}/{today}/{entity_name}.parquet"

    blob_client \
        .get_container_client("bronze") \
        .get_blob_client(blob_path) \
        .upload_blob(buffer, overwrite=True)

    print(f"  Uploaded {len(df)} rows → bronze/{blob_path}")
    return len(df)

def record_pipeline_run(conn, rows: int, status: str = "success"):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pipeline_runs
            (pipeline_name, started_at, ended_at,
             status, rows_processed, triggered_by)
        VALUES ('pl_ingest_customers', GETUTCDATE(), GETUTCDATE(), ?, ?, ?)
    """, status, rows, os.getenv("TRIGGERED_BY", "manual"))
    conn.commit()
    print(f"  Recorded: pl_ingest_customers ({status}, {rows} rows)")

def ingest(failure: str = None):
    print(f"\n=== Customer Ingestion Started (failure={failure or 'none'}) ===")

    blob   = get_blob_client()
    conn   = get_sql_connection()
    total  = 0

    try:
        print("\n[1/3] Customers...")
        customers = fetch_all_pages("customers", failure=failure)
        total += upload_to_bronze(blob, customers, "customers")

        print("\n[2/3] Customer events...")
        events = fetch_all_pages("events", page_size=200)
        total += upload_to_bronze(blob, events, "events",
                                  subfolder="customer_events")

        print("\n[3/3] Segments...")
        segments = fetch_segments()
        total += upload_to_bronze(blob, segments, "segments")

        record_pipeline_run(conn, total, "success")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        record_pipeline_run(conn, 0, "failed")
        raise

    finally:
        conn.close()

    print(f"\n=== Customer Ingestion Complete: {total} rows in Bronze ===")
    return total

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--failure",
        choices=["null_spike", "volume_drop", "schema_change"],
        default=None
    )
    args = parser.parse_args()
    ingest(failure=args.failure)