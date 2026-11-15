"""Colour tokens - the only place hex values are defined.

Categorical palettes were checked with the dataviz skill's validator (OKLab ΔE×100,
Machado 2009 CVD simulation, all pairs):
  * Lifecycle stages  pre_trial/trial/subscribed/churned -> worst CVD ΔE 11.3,
    normal-vision ΔE 18.9 (pass). Pre-trial is a deliberately neutral slate.
  * Metrics           GPV/invoices/total accounts/subscribed -> pass on adjacent
    pairs. Blue and violet are never plotted together (one metric per chart).
Colours follow the entity, never its rank, so filtering never repaints a series.
"""

# --- Surfaces & ink -------------------------------------------------------------
BACKGROUND = "#F7F8FA"
SURFACE = "#FFFFFF"
BORDER = "#E4E7EC"
GRID = "#EEF0F3"
AXIS = "#D0D5DD"
TEXT_PRIMARY = "#101828"
TEXT_SECONDARY = "#475467"
TEXT_MUTED = "#667085"

# --- Metric identity ------------------------------------------------------------
GPV = "#2A78D6"  # Blue - also the primary accent.
GPV_SECONDARY = "#86B6EF"  # Lighter step of the GPV ramp (offline share).
INVOICE = "#0F9488"  # Teal.
TOTAL_ACCOUNTS = "#6250D6"  # Violet.
SUBSCRIBED = "#008300"  # Green - same as the subscribed lifecycle stage.
PREVIOUS_PERIOD = "#B8C0CC"  # Muted grey for every previous-period comparison.

# --- Lifecycle stages (fixed mapping, used on every page) ------------------------
STAGE_PRE_TRIAL = "#A3AEBF"
STAGE_TRIAL = "#EDA100"
STAGE_SUBSCRIBED = SUBSCRIBED
STAGE_CHURNED = "#D9506A"

# --- Deltas (status: always paired with an arrow + text, never colour alone) ------
DELTA_UP = "#067647"
DELTA_DOWN = "#B42318"
DELTA_NEUTRAL = TEXT_MUTED


def with_alpha(hex_color: str, alpha: float) -> str:
    """'#RRGGBB' -> 'rgba(r,g,b,a)' for washes and fills."""
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"
