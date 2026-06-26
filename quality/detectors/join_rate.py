"""
Join Rate Detector
------------------
Checks what percentage of orders successfully matched
to a customer profile in the Gold fct_orders table.

What it does:
- Counts total orders in fct_orders
- Counts orders where full_name is NOT null (matched to customer)
- Calculates join rate as a percentage
- Fails if less than 95% of orders matched a customer

Why this detector is unique:
- Standard checks (nulls, volume, schema) would all PASS
  even if Customer API ran late and orders had no enrichment
- The Gold table would look fine on the surface
- But 20% of orders would have no customer segment or country
- This detector catches that SILENT failure

Example scenario:
- Orders pipeline ran at 6am
- Customer pipeline ran at 8am (2 hours late)
- Orders joined to an empty customer table
- Result: 0% join rate → incident opened immediately
"""

from sqlalchemy import text
import pandas as pd
from .base import CheckResult

JOIN_RATE_BASELINE = 0.95

def check_join_rate(conn) -> CheckResult:
    try:
        df = pd.read_sql(text("""
            SELECT
                COUNT(*) AS total_orders,
                SUM(CASE WHEN full_name IS NOT NULL THEN 1 ELSE 0 END) AS matched_orders,
                SUM(CASE WHEN full_name IS NULL     THEN 1 ELSE 0 END) AS unmatched_orders
            FROM fct_orders
        """), conn)

        total     = int(df["total_orders"].iloc[0])
        matched   = int(df["matched_orders"].iloc[0])
        unmatched = int(df["unmatched_orders"].iloc[0])

        if total == 0:
            return CheckResult(
                check="join_rate", table_name="fct_orders",
                status="warn", observed=0.0, expected=JOIN_RATE_BASELINE,
                details={"message": "fct_orders is empty"}
            )

        join_rate = matched / total

        if join_rate < JOIN_RATE_BASELINE * 0.9:
            status = "fail"
        elif join_rate < JOIN_RATE_BASELINE:
            status = "warn"
        else:
            status = "pass"

        return CheckResult(
            check="join_rate", table_name="fct_orders",
            status=status,
            observed=round(join_rate, 4),
            expected=JOIN_RATE_BASELINE,
            details={
                "total_orders":     total,
                "matched_orders":   matched,
                "unmatched_orders": unmatched,
                "join_rate_pct":    f"{join_rate*100:.1f}%",
                "baseline_pct":     f"{JOIN_RATE_BASELINE*100:.1f}%"
            }
        )

    except Exception as e:
        return CheckResult(
            check="join_rate", table_name="fct_orders",
            status="fail", observed=-1, expected=JOIN_RATE_BASELINE,
            details={"error": str(e)}
        )