"""Pure functions implementing the Visa VAMP and Mastercard ECM/HECM rules.

No I/O and no pandas in here, so every rule is easy to unit test.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from .config import CONFIG, Thresholds

SAFE, WATCH, BREACH = "SAFE", "WATCH", "BREACH"
_RANK = {SAFE: 0, WATCH: 1, BREACH: 2}

ECM, HECM = "ECM", "HECM"
_EPS = 1e-12


def ratio(numerator: int, denominator: Optional[int]) -> Optional[float]:
    """numerator / denominator, or None when there is no usable denominator."""
    if denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def worst_status(*statuses: str) -> str:
    return max(statuses, key=lambda s: _RANK[s])


def status_rank(status: str) -> int:
    return _RANK[status]


def _near(value: Optional[float], line: float, cfg: Thresholds) -> bool:
    return value is not None and value >= cfg.watch_fraction * line - _EPS


# ---------------------------------------------------------------- Visa VAMP

def visa_vamp_ratio(tc40_fraud: int, tc15_disputes: int, cnp_sales: int) -> Optional[float]:
    """(TC40 fraud + TC15 disputes) / settled card-not-present transactions."""
    return ratio(tc40_fraud + tc15_disputes, cnp_sales)


def visa_assess(tc40_fraud: int, tc15_disputes: int, cnp_sales: int,
                cfg: Thresholds = CONFIG) -> dict:
    """Merchant-level VAMP status for one month.

    Breach needs BOTH ratio >= 1.50% AND combined events >= 1,500. A merchant over
    the ratio line but under the floor is shown as Watch with below_floor=True.
    """
    events = tc40_fraud + tc15_disputes
    r = visa_vamp_ratio(tc40_fraud, tc15_disputes, cnp_sales)
    over_ratio = r is not None and r >= cfg.visa_merchant_ratio
    enforceable = events >= cfg.visa_merchant_floor

    if over_ratio and enforceable:
        status = BREACH
    elif over_ratio or _near(r, cfg.visa_merchant_ratio, cfg):
        status = WATCH
    else:
        status = SAFE
    return {
        "ratio": r,
        "events": events,
        "sales": cnp_sales,
        "status": status,
        "below_floor": bool(over_ratio and not enforceable),
    }


def acquirer_assess(total_events: int, total_sales: int, cfg: Thresholds = CONFIG) -> dict:
    """Book-level VAMP ratio vs the Above Standard and Excessive lines."""
    r = ratio(total_events, total_sales)
    if r is not None and r >= cfg.visa_acquirer_excessive:
        label = "EXCESSIVE"
    elif r is not None and r >= cfg.visa_acquirer_above_standard:
        label = "ABOVE STANDARD"
    elif _near(r, cfg.visa_acquirer_above_standard, cfg):
        label = "WATCH"
    else:
        label = "STANDARD"
    allowed = max_events_below(cfg.visa_acquirer_above_standard, total_sales)
    return {
        "ratio": r,
        "events": total_events,
        "sales": total_sales,
        "label": label,
        # events of headroom before the 0.50% line (negative = already over)
        "headroom_events": allowed - total_events,
    }


# ------------------------------------------------------ Mastercard ECM / HECM

def mc_ratio(chargebacks: int, prior_month_sales: Optional[int]) -> Optional[float]:
    """This month's chargebacks divided by PRIOR month's sales count."""
    return ratio(chargebacks, prior_month_sales)


def mc_assess(chargebacks: int, prior_month_sales: Optional[int],
              cfg: Thresholds = CONFIG) -> dict:
    """Single-month ECM/HECM tier. Both the count and the ratio condition are required."""
    r = mc_ratio(chargebacks, prior_month_sales)
    tier = None
    if r is not None:
        if chargebacks >= cfg.mc_hecm_count and r >= cfg.mc_hecm_ratio:
            tier = HECM
        elif chargebacks >= cfg.mc_ecm_count and r >= cfg.mc_ecm_ratio:
            tier = ECM

    near_ecm = (chargebacks >= cfg.watch_fraction * cfg.mc_ecm_count - _EPS
                and _near(r, cfg.mc_ecm_ratio, cfg))
    near_hecm = (tier == ECM
                 and chargebacks >= cfg.watch_fraction * cfg.mc_hecm_count - _EPS
                 and _near(r, cfg.mc_hecm_ratio, cfg))
    if tier:
        status = BREACH
    elif near_ecm:
        status = WATCH
    else:
        status = SAFE
    return {
        "ratio": r,
        "chargebacks": chargebacks,
        "prior_sales": prior_month_sales,
        "tier": tier,
        "near_hecm": near_hecm,
        "status": status,
    }


def ecm_program_states(tiers: Sequence[Optional[str]],
                       cfg: Thresholds = CONFIG) -> list:
    """Walk monthly tiers in order and track ECM program membership.

    A merchant enters on any ECM/HECM month and exits only after
    `ecm_exit_clean_months` consecutive months under the ECM thresholds.
    """
    in_program, clean = False, 0
    out = []
    for tier in tiers:
        if tier in (ECM, HECM):
            in_program, clean = True, 0
        elif in_program:
            clean += 1
            if clean >= cfg.ecm_exit_clean_months:
                in_program, clean = False, 0
        out.append({"in_program": in_program, "clean_months": clean if in_program else 0})
    return out


# ------------------------------------------------------------------ what-if

def max_events_below(line: float, base: int) -> int:
    """Largest whole number of events that keeps events/base strictly below `line`."""
    if base <= 0:
        return 0
    n = math.ceil(line * base) - 1
    while n >= 0 and n / base >= line:
        n -= 1
    while (n + 1) / base < line:
        n += 1
    return max(n, 0)


def visa_what_if(events: int, cnp_sales: int, cfg: Thresholds = CONFIG) -> dict:
    """Fewer TC40+TC15 events next month (same volume) to drop out of VAMP enforcement.

    Enforcement needs ratio >= 1.50% AND events >= 1,500, so getting under either
    condition is enough; report whichever needs fewer cuts.
    """
    under_ratio = max_events_below(cfg.visa_merchant_ratio, cnp_sales)
    under_floor = cfg.visa_merchant_floor - 1
    if under_ratio >= under_floor:
        target, route = under_ratio, f"ratio below {cfg.visa_merchant_ratio:.2%}"
    else:
        target, route = under_floor, f"events below the {cfg.visa_merchant_floor:,} floor"
    return {
        "events_now": events,
        "target_events": target,
        "cut": max(0, events - target),
        "route": route,
    }


def mc_what_if(chargebacks_now: int, this_month_sales: int,
               cfg: Thresholds = CONFIG) -> dict:
    """Fewer chargebacks next month (measured against this month's sales) to get under each line."""
    def one(count_line: int, ratio_line: float, name: str) -> dict:
        under_ratio = max_events_below(ratio_line, this_month_sales)
        under_count = count_line - 1
        if under_ratio >= under_count:
            target, route = under_ratio, f"ratio below {ratio_line:.2%}"
        else:
            target, route = under_count, f"chargebacks below {count_line}"
        return {"program": name, "target_chargebacks": target,
                "cut": max(0, chargebacks_now - target), "route": route}

    return {
        "chargebacks_now": chargebacks_now,
        "ecm": one(cfg.mc_ecm_count, cfg.mc_ecm_ratio, ECM),
        "hecm": one(cfg.mc_hecm_count, cfg.mc_hecm_ratio, HECM),
        "exit_months": cfg.ecm_exit_clean_months,
    }
