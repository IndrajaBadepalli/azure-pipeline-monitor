"""
Alerting System
---------------
Sends notifications when a data quality incident is created.

Two channels:
1. Microsoft Teams webhook — instant notification in Teams channel
2. Azure Logic App — sends formatted email

How to run:
  python alerting/send_alerts.py --incident <incident-id>

Setup required:
  TEAMS_WEBHOOK_URL — get from Teams channel → Connectors → Incoming Webhook
  LOGIC_APP_EMAIL_URL — get from Azure Logic App HTTP trigger URL
"""

import os
import json
import argparse
import requests
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

def get_incident(incident_id: str) -> dict:
    """Fetch incident details from Azure SQL."""
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(f"""
            SELECT
                CAST(incident_id AS NVARCHAR(200)) AS incident_id,
                severity, summary, rca_text,
                suggested_fix, status,
                CAST(created_at AS DATETIME2) AS created_at
            FROM incidents
            WHERE CAST(incident_id AS NVARCHAR(200)) = '{incident_id}'
        """), conn)
    if df.empty:
        raise ValueError(f"Incident {incident_id} not found")
    return df.iloc[0].to_dict()

def send_teams_alert(incident: dict) -> bool:
    """
    Send alert to Microsoft Teams via Incoming Webhook.
    Teams uses Adaptive Cards for rich formatted messages.
    """
    webhook_url = os.getenv("TEAMS_WEBHOOK_URL")
    if not webhook_url:
        print("  ⚠️  TEAMS_WEBHOOK_URL not configured — skipping Teams alert")
        return False

    # Severity color coding
    severity_colors = {
        "critical": "FF0000",  # Red
        "high":     "FF6600",  # Orange
        "medium":   "FFCC00",  # Yellow
        "low":      "00CC00",  # Green
    }
    color = severity_colors.get(incident["severity"], "FFCC00")

    # Teams Adaptive Card payload
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type":    "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {
                        "type":   "TextBlock",
                        "text":   f"🚨 Data Pipeline Incident — {incident['severity'].upper()}",
                        "weight": "Bolder",
                        "size":   "Large",
                        "color":  "Attention"
                    },
                    {
                        "type": "FactSet",
                        "facts": [
                            {"title": "Incident ID", "value": str(incident["incident_id"])},
                            {"title": "Severity",    "value": incident["severity"].upper()},
                            {"title": "Status",      "value": incident["status"]},
                            {"title": "Summary",     "value": incident["summary"]},
                        ]
                    },
                    {
                        "type": "TextBlock",
                        "text": f"**Root Cause:** {incident.get('rca_text') or 'RCA pending'}",
                        "wrap": True
                    },
                    {
                        "type": "TextBlock",
                        "text": f"**Suggested Fix:** {incident.get('suggested_fix') or 'See RCA analyzer'}",
                        "wrap": True
                    }
                ]
            }
        }]
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("  ✅ Teams alert sent")
            return True
        else:
            print(f"  ❌ Teams alert failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"  ❌ Teams alert error: {e}")
        return False

def send_email_alert(incident: dict) -> bool:
    """
    Send email via Azure Logic App HTTP trigger.
    Logic App handles the actual email sending via Office 365.
    """
    logic_app_url = os.getenv("LOGIC_APP_EMAIL_URL")
    if not logic_app_url:
        print("  ⚠️  LOGIC_APP_EMAIL_URL not configured — skipping email alert")
        return False

    payload = {
        "incident_id":   str(incident["incident_id"]),
        "severity":      incident["severity"],
        "summary":       incident["summary"],
        "rca_text":      incident.get("rca_text") or "RCA pending",
        "suggested_fix": incident.get("suggested_fix") or "See RCA analyzer",
        "dashboard_url": os.getenv("DASHBOARD_URL", "http://localhost:8501")
    }

    try:
        resp = requests.post(logic_app_url, json=payload, timeout=15)
        if resp.status_code in (200, 202):
            print("  ✅ Email alert sent via Logic App")
            return True
        else:
            print(f"  ❌ Email alert failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"  ❌ Email alert error: {e}")
        return False

def send_all_alerts(incident_id: str):
    print(f"\n=== Sending Alerts for Incident {incident_id} ===")

    incident = get_incident(incident_id)

    print(f"\n  Incident: {incident['summary']}")
    print(f"  Severity: {incident['severity'].upper()}")

    teams_sent = send_teams_alert(incident)
    email_sent = send_email_alert(incident)

    if not teams_sent and not email_sent:
        print("\n  ⚠️  No alert channels configured.")
        print("  Add TEAMS_WEBHOOK_URL or LOGIC_APP_EMAIL_URL to your .env file")
    else:
        print(f"\n  ✅ Alerts sent successfully")

    return teams_sent or email_sent

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", required=True,
                        help="Incident UUID to alert on")
    args = parser.parse_args()
    send_all_alerts(args.incident)