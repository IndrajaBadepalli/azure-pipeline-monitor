"""
Freshness Detector
------------------
Checks if the most recent record in a table is within the SLA window.
Uses database server time for comparison to avoid timezone issues.
"""

from sqlalchemy import text
import pandas as pd
from .base import CheckResult

def check_freshness(table: str, sla_hours: int, conn, date_column: str = "ingested_at") -> CheckResult:
    try:
        df = pd.read_sql(text(f"""
            SELECT DATEDIFF(hour, MAX({date_column}), GETUTCDATE()) AS age_hours
            FROM {table}
        """), conn)

        age_hours = df["age_hours"].iloc[0]

        if age_hours is None:
            return CheckResult(
                check="freshness", table_name=table,
                status="fail", observed=999, expected=sla_hours,
                details={"error": "No records found in table"}
            )

        age_hours = float(age_hours)

        if age_hours > sla_hours:
            status = "fail"
        elif age_hours > sla_hours * 0.8:
            status = "warn"
        else:
            status = "pass"

        return CheckResult(
            check="freshness", table_name=table,
            status=status,
            observed=round(age_hours, 2),
            expected=sla_hours,
            details={"date_column": date_column, "age_hours": round(age_hours, 2), "sla_hours": sla_hours}
        )

    except Exception as e:
        return CheckResult(
            check="freshness", table_name=table,
            status="fail", observed=-1, expected=sla_hours,
            details={"error": str(e)}
        )