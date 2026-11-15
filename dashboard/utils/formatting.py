"""Number formatting - the single source of display rules for the whole app.

Compact (cards, axes, bar labels):  $1.97M · $450K · $45.2K · $950 · 1,234 · 12.3K
Full (tooltips, tables):            $1,968,622.53 · 1,234
"""

from __future__ import annotations

import math

_SUFFIXES = ((1e3, "K"), (1e6, "M"), (1e9, "B"))


def _compact(value: float) -> str:
    """Three significant figures with a K/M/B suffix (values >= 1,000)."""
    magnitude = abs(value)
    if round(magnitude) < 1000:
        return f"{value:,.0f}"
    index = max(i for i, (threshold, _) in enumerate(_SUFFIXES)
                if magnitude >= threshold or i == 0)
    scaled = magnitude / _SUFFIXES[index][0]
    decimals = 2 if scaled < 10 else 1 if scaled < 100 else 0
    # Rounding can overflow into the next suffix (999,999 -> "1000K" -> "1M").
    if round(scaled, decimals) >= 1000 and index < len(_SUFFIXES) - 1:
        index += 1
        scaled, decimals = magnitude / _SUFFIXES[index][0], 2
    text = f"{scaled:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{'-' if value < 0 else ''}{text}{_SUFFIXES[index][1]}"


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def usd_compact(value) -> str:
    if _is_missing(value):
        return "—"
    sign = "-" if value < 0 else ""
    return f"{sign}${_compact(abs(value))}"


def usd_full(value) -> str:
    if _is_missing(value):
        return "—"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def count_full(value) -> str:
    if _is_missing(value):
        return "—"
    return f"{value:,.0f}"


def count_compact(value) -> str:
    if _is_missing(value):
        return "—"
    return _compact(value) if abs(value) >= 10_000 else f"{value:,.0f}"


def percent(value, decimals: int = 1) -> str:
    """Format a ratio (0.305 -> '30.5%')."""
    if _is_missing(value):
        return "—"
    return f"{value * 100:.{decimals}f}%"


def pct_change(current, previous) -> float | None:
    """Relative change, or None when the base is zero/missing (never a fake %)."""
    if _is_missing(current) or _is_missing(previous) or previous == 0:
        return None
    return (current - previous) / abs(previous)


def signed_percent(value) -> str:
    if value is None:
        return "—"
    return f"{'+' if value > 0 else ''}{value * 100:.1f}%"


def format_value(value, kind: str, compact: bool = True) -> str:
    """Dispatch on metric kind: 'currency' or 'count'."""
    if kind == "currency":
        return usd_compact(value) if compact else usd_full(value)
    return count_compact(value) if compact else count_full(value)


def nice_ticks(max_value: float, target: int = 5) -> list[float]:
    """Round axis ticks from 0 to just above max_value (1/2/2.5/5 x 10^n steps)."""
    if not max_value or max_value <= 0 or math.isnan(max_value):
        return [0, 1]
    raw_step = max_value / target
    power = 10 ** math.floor(math.log10(raw_step))
    step = next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= raw_step)
    count = math.ceil(max_value / step)
    return [round(i * step, 10) for i in range(count + 1)]
