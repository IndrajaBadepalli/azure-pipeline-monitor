"""
Volume Detector
---------------
Checks if today's row count is within normal range
using 3-sigma statistical baselining.

What it does:
- Gets the last 7 days of successful pipeline run row counts
- Calculates mean and standard deviation
- If today's count is more than 3 standard deviations away → fail
- If more than 2 standard deviations away → warn

Why it matters:
- A sudden drop in rows means data was lost or not ingested
- A sudden spike means duplicate data was loaded
- Example: normally 500 rows, today only 50 → volume_drop failure

What is 3-sigma?
- Mean = average of last 7 days
- Standard deviation = how much variation is normal
- Z-score = (today - mean) / std
- Z-score > 3 means today is statistically abnormal (99.7% rule)
"""

from sqlalchemy import text
import pandas as pd
from .base import CheckResult

def check_volume(pipeline_name: str, current_count: int, conn) -> CheckResult:
    try:
        history_df = pd.read_sql(text(f"""
            SELECT rows_processed
            FROM pipeline_runs
            WHERE pipeline_name = '{pipeline_name}'
              AND status = 'success'
              AND ended_at >= DATEADD(day, -7, GETUTCDATE())
        """), conn)

        if len(history_df) < 3:
            return CheckResult(
                check="row_count", table_name=pipeline_name,
                status="warn", observed=current_count, expected=0,
                details={"message": "Not enough history (need 3+ runs)"}
            )

        mean = history_df["rows_processed"].mean()
        std  = history_df["rows_processed"].std()

        z_score = 0 if std == 0 else abs((current_count - mean) / std)

        if z_score > 3:
            status = "fail"
        elif z_score > 2:
            status = "warn"
        else:
            status = "pass"

        return CheckResult(
            check="row_count", table_name=pipeline_name,
            status=status,
            observed=current_count,
            expected=round(mean, 0),
            details={
                "z_score":      round(float(z_score), 2),
                "mean_7d":      round(float(mean), 0),
                "std_7d":       round(float(std), 0),
                "history_runs": len(history_df)
            }
        )

    except Exception as e:
        return CheckResult(
            check="row_count", table_name=pipeline_name,
            status="fail", observed=current_count, expected=-1,
            details={"error": str(e)}
        )