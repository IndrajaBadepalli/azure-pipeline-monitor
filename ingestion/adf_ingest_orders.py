"""
Orders Ingestion Script
-----------------------
What it does:
  1. Calls the Mock Orders API (all pages)
  2. Calls the Mock Orders API for products
  3. Converts both to Parquet format
  4. Uploads to ADLS Gen2 Bronze container
  5. Records the pipeline run in Azure SQL

How to run:
  python ingestion/adf_ingest_orders.py
  python ingestion/adf_ingest_orders.py --failure null_spike
  python ingestion/adf_ingest_orders.py --failure volume_drop
  python ingestion/adf_ingest_orders.py --failure late_data
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

def fetch_all_orders(failure: str = None) -> list:
    api_url    = os.getenv("MOCK_API_URL", "http://localhost:8000")
    all_orders = []
    page       = 1

    while True:
        params = {"page": page, "page_size": 100}
        if failure:
            params["failure"] = failure

        print(f"  Fetching orders page {page}...")
        response = requests.get(f"{api_url}/orders", params=params, timeout=15)
        response.raise_for_status()

        data = response.json()
        all_orders.extend(data["data"])

        if len(all_orders) >= data["total"]:
            break
        page += 1

    print(f"  Total orders fetched: {len(all_orders)}")
    return all_orders

def fetch_products() -> list:
    api_url  = os.getenv("MOCK_API_URL", "http://localhost:8000")
    response = requests.get(f"{api_url}/products", timeout=15)
    response.raise_for_status()
    return response.json()["data"]

def upload_to_bronze(blob_client: BlobServiceClient,
                     data: list,
                     entity_name: str) -> int:
    df = pd.DataFrame(data)
    df["ingested_at"]  = datetime.utcnow().isoformat()
    df["adf_pipeline"] = "pl_ingest_orders"

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    today     = datetime.utcnow().strftime("%Y/%m/%d")
    blob_path = f"{entity_name}/{today}/{entity_name}.parquet"

    blob_client \
        .get_container_client("bronze") \
        .get_blob_client(blob_path) \
        .upload_blob(buffer, overwrite=True)

    print(f"  Uploaded {len(df)} rows → bronze/{blob_path}")
    return len(df)

def record_pipeline_run(conn, pipeline_name: str,
                        rows: int, status: str = "success"):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pipeline_runs
            (pipeline_name, started_at, ended_at,
             status, rows_processed, triggered_by)
        VALUES (?, GETUTCDATE(), GETUTCDATE(), ?, ?, ?)
    """, pipeline_name, status, rows,
         os.getenv("TRIGGERED_BY", "manual"))
    conn.commit()
    print(f"  Recorded pipeline run: {pipeline_name} ({status}, {rows} rows)")

def ingest(failure: str = None):
    print(f"\n=== Orders Ingestion Started (failure={failure or 'none'}) ===")

    blob_client = get_blob_client()
    sql_conn    = get_sql_connection()
    total_rows  = 0

    try:
        print("\n[1/2] Fetching and uploading orders...")
        orders    = fetch_all_orders(failure=failure)
        total_rows += upload_to_bronze(blob_client, orders, "orders")

        print("\n[2/2] Fetching and uploading products...")
        products  = fetch_products()
        total_rows += upload_to_bronze(blob_client, products, "products")

        record_pipeline_run(sql_conn, "pl_ingest_orders", total_rows, "success")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        record_pipeline_run(sql_conn, "pl_ingest_orders", 0, "failed")
        raise

    finally:
        sql_conn.close()

    print(f"\n=== Orders Ingestion Complete: {total_rows} rows in Bronze ===")
    return total_rows

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--failure",
        choices=["null_spike", "volume_drop", "late_data"],
        default=None,
        help="Type of failure to inject for testing"
    )
    args = parser.parse_args()
    ingest(failure=args.failure)