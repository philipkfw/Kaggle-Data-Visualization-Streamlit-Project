"""Dashboard filter state and its translation to SQL predicates.

Segment values are always passed as bind parameters. Column names come only from
the fixed dimension allow-list in metrics.DIMENSIONS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dashboard.domain.metrics import DIMENSION_KEYS
from dashboard.utils.date_utils import Period, comparison_period


@dataclass(frozen=True)
class SegmentFilters:
    """Multi-select segment filters. An empty tuple means 'all'."""

    country: tuple[str, ...] = ()
    region: tuple[str, ...] = ()
    city: tuple[str, ...] = ()
    sign_up_platform: tuple[str, ...] = ()

    def selections(self) -> dict[str, tuple[str, ...]]:
        return {key: getattr(self, key) for key in
                ("country", "region", "city", "sign_up_platform") if getattr(self, key)}

    @property
    def is_active(self) -> bool:
        return bool(self.selections())

    def to_sql(self, alias: str = "") -> tuple[str, dict]:
        """Return (`AND ...` predicate string, bind params)."""
        prefix = f"{alias}." if alias else ""
        clauses, params = [], {}
        for column, values in self.selections().items():
            if column not in DIMENSION_KEYS:  # Defensive: allow-list only.
                raise ValueError(f"Unknown dimension {column!r}")
            names = []
            for i, value in enumerate(values):
                name = f"f_{column}_{i}"
                params[name] = value
                names.append(f"%({name})s")
            clauses.append(f"{prefix}{column} IN ({', '.join(names)})")
        sql = "".join(f"\n    AND {clause}" for clause in clauses)
        return sql, params


@dataclass(frozen=True)
class DashboardFilters:
    period: Period
    data_window: Period
    segments: SegmentFilters = field(default_factory=SegmentFilters)

    @property
    def comparison(self) -> Period | None:
        return comparison_period(self.period, self.data_window)
