"""
Null Rate Detector
------------------
Checks if the null rate for a critical column has spiked
above its known baseline.

What it does:
- Counts total rows and null rows for a specific column
- Calculates null rate as a percentage
- Compares to the known baseline null rate
- Fails if null rate is 3x the baseline OR above 5%

Why it matters:
- A null spike means the source system had a problem
- Example: amount column normally 0.1% null, today 14% null
- This means 14% of orders have no amount — broken data

Baseline null rates are defined per column.
In production these would be learned automatically from history.
"""

from sqlalchemy import text
import pandas as pd
from .base import CheckResult

BASELINE_NULL_RATES = {
    "fct_orders.amount":      0.001,
    "fct_orders.customer_id": 0.0,
    "fct_orders.order_date":  0.0,
    "dim_customers.email":    0.001,
}

def check_null_rate(table: str, column: str, conn) -> CheckResult:
    try:
        df = pd.read_sql(text(f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN [{column}] IS NULL THEN 1 ELSE 0 END) AS nulls
            FROM {table}
        """), conn)

        total = int(df["total"].iloc[0])
        nulls = int(df["nulls"].iloc[0])

        if total == 0:
            return CheckResult(
                check="null_rate", table_name=f"{table}.{column}",
                status="warn", observed=0, expected=0,
                details={"message": "Table is empty"}
            )

        null_rate = nulls / total
        baseline  = BASELINE_NULL_RATES.get(f"{table}.{column}", 0.01)

        if null_rate > baseline * 3 or (null_rate > 0.05 and baseline < 0.005):
            status = "fail"
        elif null_rate > baseline * 1.5:
            status = "warn"
        else:
            status = "pass"

        return CheckResult(
            check="null_rate", table_name=f"{table}.{column}",
            status=status,
            observed=round(float(null_rate), 4),
            expected=baseline,
            details={
                "column":       column,
                "total_rows":   total,
                "null_count":   nulls,
                "null_pct":     f"{null_rate*100:.2f}%",
                "baseline_pct": f"{baseline*100:.2f}%"
            }
        )

    except Exception as e:
        return CheckResult(
            check="null_rate", table_name=f"{table}.{column}",
            status="fail", observed=-1, expected=-1,
            details={"error": str(e)}
        )