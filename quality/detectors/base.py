"""
Base class for all quality check results.
Every detector returns a CheckResult object.
"""

from dataclasses import dataclass, field
from typing import Any

@dataclass
class CheckResult:
    check:      str      # name of the check (freshness, volume, etc.)
    table_name: str      # which table was checked
    status:     str      # pass | warn | fail
    observed:   float    # what we actually saw
    expected:   float    # what we expected to see
    details:    dict = field(default_factory=dict)  # extra info

    def to_dict(self):
        """Convert to dictionary for saving to Azure SQL."""
        return {
            "check_name":     self.check,
            "table_name":     self.table_name,
            "status":         self.status,
            "observed_value": self.observed,
            "expected_value": self.expected,
            "details":        str(self.details)
        }