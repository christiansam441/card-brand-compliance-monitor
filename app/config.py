"""Program thresholds. Every rule in rules.py reads from here; nothing is hard-coded elsewhere.

Values come from public acquirer/processor documentation (Mastercard's own
manuals are not public), so treat them as a documented assumption.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Thresholds:
    # Visa VAMP, merchant level
    visa_merchant_ratio: float = 0.015      # Excessive at >= 1.50%
    visa_merchant_floor: int = 1500         # ...and only if combined events >= 1,500 in the month

    # Visa VAMP, acquirer level (whole book)
    visa_acquirer_above_standard: float = 0.005   # >= 0.50%
    visa_acquirer_excessive: float = 0.007        # >= 0.70%

    # Mastercard ECM / HECM (chargebacks this month / sales count PRIOR month)
    mc_ecm_count: int = 100
    mc_ecm_ratio: float = 0.015
    mc_hecm_count: int = 300
    mc_hecm_ratio: float = 0.03
    ecm_exit_clean_months: int = 3          # consecutive months under ECM thresholds to exit

    # "Watch" = within this fraction of the line (but not over it)
    watch_fraction: float = 0.8


CONFIG = Thresholds()

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "merchant_months.csv"
