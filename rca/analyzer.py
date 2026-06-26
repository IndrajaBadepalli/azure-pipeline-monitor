"""
RCA Analyzer
------------
Sends incident context to Groq LLM and gets root cause analysis.

What it does:
1. Builds context bundle (failing checks + run history + schema diff)
2. Sends to Groq LLM with a structured prompt
3. Gets back ranked hypotheses + suggested fix in JSON
4. Saves RCA to incidents table in Azure SQL
5. Prints the diagnosis

How to run:
  python rca/analyzer.py --incident <incident-id>
"""

import os
import json
import argparse
import pyodbc
from groq import Groq
from dotenv import load_dotenv
from rca.context_builder import build_context, get_connection

load_dotenv()

# System prompt — tells the LLM exactly what to do
SYSTEM_PROMPT = """
You are a senior Azure data engineer performing incident triage
on a data pipeline monitoring platform.

Given failing data quality checks, recent pipeline run history,
and schema diffs, produce a root cause analysis.

Respond ONLY with valid JSON — no markdown, no text outside JSON.

Use exactly this structure:
{
  "summary": "one clear sentence describing the root cause",
  "severity": "low or medium or high or critical",
  "ranked_hypotheses": [
    {
      "rank": 1,
      "hypothesis": "what likely happened",
      "confidence": "high or medium or low",
      "evidence": "which check or metric supports this"
    }
  ],
  "suggested_fix": "concrete step by step fix for the engineer",
  "is_upstream_issue": true or false,
  "affected_tables": ["list", "of", "affected", "tables"]
}
"""

def call_groq(context: dict) -> dict:
    """Send context to Groq LLM and get structured JSON response."""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    user_message = f"""
Incident summary: {context["incident_summary"]}
Severity: {context["severity"]}

Failing checks:
{json.dumps(context["failing_checks"], indent=2, default=str)}

Recent pipeline run history (last 10):
{json.dumps(context["run_history"], indent=2, default=str)}

Schema diff (if any):
{json.dumps(context["schema_diff"], indent=2, default=str)}
"""

    response = client.chat.completions.create(
        model    = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message}
        ],
        temperature     = 0.2,
        max_tokens      = 1000,
        response_format = {"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)

def save_rca(incident_id: str, rca: dict, context: dict):
    """Save RCA results back to the incidents table."""
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE incidents
        SET rca_text      = ?,
            suggested_fix = ?,
            context_bundle = ?,
            severity      = ?
        WHERE CAST(incident_id AS NVARCHAR(200)) = ?
    """,
        rca.get("summary", ""),
        rca.get("suggested_fix", ""),
        json.dumps(context, default=str),
        rca.get("severity", "medium"),
        incident_id
    )
    conn.commit()
    conn.close()

def analyze_incident(incident_id: str):
    print(f"\n=== RCA Analyzer ===")
    print(f"  Incident: {incident_id}")

    # Build context
    print(f"\n  Building context...")
    context = build_context(incident_id)

    # Call Groq LLM
    print(f"  Calling Groq ({os.getenv('GROQ_MODEL')})...")
    rca = call_groq(context)

    # Print results
    print(f"\n=== ROOT CAUSE ANALYSIS ===")
    print(f"\n  Summary:  {rca.get('summary')}")
    print(f"  Severity: {rca.get('severity','').upper()}")
    print(f"\n  Hypotheses:")
    for h in rca.get("ranked_hypotheses", []):
        print(f"    {h['rank']}. [{h['confidence'].upper()}] {h['hypothesis']}")
        print(f"       Evidence: {h['evidence']}")
    print(f"\n  Suggested Fix:")
    print(f"    {rca.get('suggested_fix')}")
    print(f"\n  Upstream issue: {rca.get('is_upstream_issue')}")
    print(f"  Affected tables: {rca.get('affected_tables')}")

    # Save to Azure SQL
    save_rca(incident_id, rca, context)
    print(f"\n  ✅ RCA saved to incidents table")

    return rca

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", required=True,
                        help="Incident UUID to analyze")
    args = parser.parse_args()
    analyze_incident(args.incident)