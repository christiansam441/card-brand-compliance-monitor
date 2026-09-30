"""Seeded synthetic data generator. All data is fake; nothing here touches a real system.

Produces data/merchant_months.csv: 40 merchants x 7 monthly rollups. The first month is a
baseline that only supplies the "prior month sales" denominator for Mastercard ratios, so
6 months are actually evaluated (2026-04 .. 2026-09).

Six merchants are planted by name (M001-M006). The other 34 are clean, and their event
rates are scaled so the acquirer book lands just under 0.50% without M006 and just over
0.50% with it.

Run:  python scripts/generate_data.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import CONFIG  # noqa: E402

SEED = 20260930
MONTHS = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
T = len(MONTHS)
LAST = T - 1
N_MERCHANTS = 40

TARGET_WITHOUT_M6 = 0.00493   # book ratio excluding M006 (just under 0.50%)
TARGET_WITH_M6 = 0.00506      # book ratio including M006 (just over 0.50%)

VERTICALS = {
    "nutraceuticals": ["Nutrition", "Labs", "Vitamins"],
    "CBD": ["Botanicals", "Hemp Co", "Wellness"],
    "telehealth": ["Health", "Care", "Clinic Online"],
    "med spa": ["Aesthetics", "Med Spa", "Skin Clinic"],
    "subscription box": ["Box", "Crate", "Club"],
    "apparel e-commerce": ["Apparel", "Threads", "Outfitters"],
    "electronics": ["Gadgets", "Electronics", "Tech"],
    "software / SaaS": ["Software", "Cloud", "Systems"],
    "travel": ["Travel", "Getaways", "Tours"],
    "home goods": ["Home", "Living", "Goods"],
    "digital goods": ["Digital", "Media", "Games"],
    "fitness": ["Fitness", "Athletics", "Gear"],
    "beauty / skincare": ["Beauty", "Skincare", "Cosmetics"],
    "pet supplies": ["Pet Supply", "Paws", "Pet Co"],
    "online education": ["Academy", "Learning", "Courses"],
}
PREFIXES = [
    "Summit", "Harbor", "Cedar", "Copper", "Lumen", "Atlas", "Willow", "Ember", "Orchard",
    "Quartz", "Falcon", "Maple", "Nimbus", "Ridge", "Saffron", "Tidal", "Vista", "Yarrow",
    "Zephyr", "Bright", "Crest", "Delta", "Elm", "Flint", "Glen", "Hollow", "Iris", "Kestrel",
    "Lark", "Mosaic", "Nova", "Onyx", "Pine", "Quill", "Raven", "Sage", "Thistle", "Umber",
    "Vale", "Wren",
]

# Planted merchants. *_rate lists are per month; Visa events = sales * rate, Mastercard
# chargebacks = rate * PRIOR month's MC sales (the same basis the rule uses).
PLANTED = {
    "M001": dict(  # 1. clean merchant for contrast (generated like any clean merchant)
        name="Juniper Home Goods", vertical="home goods", generic=True,
        visa_sales=[24000, 24500, 25200, 24800, 25600, 26100, 26400],
        mc_sales=[15000, 15200, 15600, 15400, 15900, 16200, 16300]),
    "M002": dict(  # 2. breaches Visa VAMP only
        name="Vantage Vitamins", vertical="nutraceuticals",
        visa_sales=[104000, 106000, 108000, 110000, 111000, 113000, 114000],
        visa_rate=[.0085, .0095, .0110, .0125, .0140, .0158, .0168],
        mc_sales=[21000, 21500, 21800, 22000, 22300, 22500, 22800],
        mc_rate=[.0012, .0014, .0011, .0013, .0012, .0014, .0012]),
    "M003": dict(  # 3. breaches Mastercard ECM only (Visa far below the floor)
        name="Bayline Telehealth", vertical="telehealth",
        visa_sales=[9000, 9100, 9200, 9300, 9400, 9500, 9600],
        visa_rate=[.0025, .0027, .0024, .0026, .0025, .0027, .0026],
        mc_sales=[7800, 8000, 8200, 8100, 8300, 8400, 8400],
        mc_rate=[.004, .006, .008, .010, .013, .016, .0175]),
    "M004": dict(  # 4. fast growth: ratio on PRIOR sales looks inflated
        name="Skyrocket Fit Box", vertical="subscription box",
        visa_sales=[14000, 15500, 17000, 19000, 21500, 24000, 27000],
        visa_rate=[.0022, .0024, .0021, .0023, .0022, .0024, .0023],
        mc_sales=[9000, 10000, 12000, 15000, 18500, 22000, 27000],
        mc_rate=[.004, .005, .007, .009, .011, .0135, .016]),
    "M005": dict(  # 5. trending toward HECM (300+ and 3%)
        name="Green Canyon CBD", vertical="CBD",
        visa_sales=[11000, 11300, 11600, 12000, 12300, 12600, 13000],
        visa_rate=[.0030, .0028, .0031, .0029, .0030, .0032, .0030],
        mc_sales=[11000, 11500, 11800, 12200, 12500, 12800, 13000],
        mc_rate=[.005, .009, .011, .016, .020, .023, .0265]),
    "M006": dict(  # 6. small merchant that tips the acquirer book over 0.50%
        name="Pocket Peak Gadgets", vertical="electronics",
        visa_sales=[5200, 5600, 6200, 6800, 7200, 7600, 8000],
        visa_rate=[.004, .005, .008, .011, .015, .018, None],  # last month derived below
        mc_sales=[4200, 4500, 4800, 5100, 5400, 5700, 6000],
        mc_rate=[.0020, .0022, .0018, .0021, .0020, .0019, .0021]),
}


def _merchant_identities(rng: np.random.Generator) -> list:
    """M001..M040 with names/verticals; planted ones keep their fixed identity."""
    taken = {p["name"] for p in PLANTED.values()}
    prefixes = list(PREFIXES)
    rng.shuffle(prefixes)
    verticals = list(VERTICALS)
    out = []
    for i in range(1, N_MERCHANTS + 1):
        mid = f"M{i:03d}"
        if mid in PLANTED:
            out.append((mid, PLANTED[mid]["name"], PLANTED[mid]["vertical"]))
            continue
        vertical = verticals[int(rng.integers(len(verticals)))]
        while True:
            name = f"{prefixes.pop()} {VERTICALS[vertical][int(rng.integers(3))]}"
            if name not in taken:
                break
        taken.add(name)
        out.append((mid, name, vertical))
    return out


def _generic_series(rng: np.random.Generator) -> dict:
    base = float(np.clip(rng.lognormal(math.log(16000), 0.6), 2500, 48000))
    drift = rng.uniform(-0.02, 0.03)
    visa_sales = [int(base * (1 + drift * t) * rng.uniform(0.95, 1.05)) for t in range(T)]
    mc_sales = [int(v * rng.uniform(0.55, 1.0)) for v in visa_sales]
    return dict(visa_sales=visa_sales, mc_sales=mc_sales)


def generate() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    ids = _merchant_identities(rng)

    merchants = {}
    for mid, name, vertical in ids:
        mrng = np.random.default_rng([SEED, int(mid[1:])])
        spec = PLANTED.get(mid)
        if spec is None or spec.get("generic"):
            series = _generic_series(mrng)
            if spec:  # keep M001's hand-set volumes
                series = dict(visa_sales=spec["visa_sales"], mc_sales=spec["mc_sales"])
            base_v = mrng.uniform(0.0010, 0.0040)
            base_c = mrng.uniform(0.0010, 0.0050)
            series["visa_rate_f"] = [base_v * mrng.uniform(0.85, 1.15) for _ in range(T)]
            series["mc_rate"] = [base_c * mrng.uniform(0.85, 1.15) for _ in range(T)]
            series["clean"] = True
        else:
            series = dict(visa_sales=spec["visa_sales"], mc_sales=spec["mc_sales"],
                          mc_rate=spec["mc_rate"], visa_rate=spec["visa_rate"], clean=False)
        series.update(mid=mid, name=name, vertical=vertical, rng=mrng)
        series["ticket"] = float(mrng.uniform(48, 160))
        series["split"] = float(mrng.uniform(0.35, 0.5))
        merchants[mid] = series

    # Planted (non-clean) Visa events; M006's final month is solved for after the book total is known.
    events = {}
    for mid, m in merchants.items():
        if not m["clean"]:
            events[mid] = [None if r is None else int(round(s * r))
                           for s, r in zip(m["visa_sales"], m["visa_rate"])]

    s_last = {mid: m["visa_sales"][LAST] for mid, m in merchants.items()}
    total_sales = sum(s_last.values())
    sales_without_m6 = total_sales - s_last["M006"]

    planted_last = sum(events[mid][LAST] for mid in ("M002", "M003", "M004", "M005"))
    target_without = int(round(TARGET_WITHOUT_M6 * sales_without_m6))
    clean_ids = [mid for mid, m in merchants.items() if m["clean"]]
    clean_needed = target_without - planted_last

    def clean_events(k: float) -> dict:
        return {mid: [int(round(merchants[mid]["visa_sales"][t] * merchants[mid]["visa_rate_f"][t] * k))
                      for t in range(T)] for mid in clean_ids}

    lo, hi = 0.1, 5.0
    for _ in range(60):
        mid_k = (lo + hi) / 2
        if sum(v[LAST] for v in clean_events(mid_k).values()) < clean_needed:
            lo = mid_k
        else:
            hi = mid_k
    ev = clean_events(hi)
    residual = clean_needed - sum(v[LAST] for v in ev.values())
    i = 0
    while residual != 0:  # exact integer landing, one event at a time
        mid = clean_ids[i % len(clean_ids)]
        step = 1 if residual > 0 else -1
        ev[mid][LAST] += step
        residual -= step
        i += 1
    events.update(ev)

    e_without = sum(events[mid][LAST] for mid in merchants if mid != "M006")
    e6 = math.ceil(TARGET_WITH_M6 * total_sales) - e_without
    events["M006"][LAST] = e6

    rows = []
    for mid, m in merchants.items():
        r = m["rng"]
        cb_prev = None
        for t in range(T):
            ev_t = events[mid][t]
            fraud = int(round(ev_t * m["split"]))
            disputes = ev_t - fraud
            mc_sales = m["mc_sales"][t]
            prior = m["mc_sales"][t - 1] if t > 0 else mc_sales
            cb = int(round(m["mc_rate"][t] * prior))
            mc_fraud = int(round(mc_sales * r.uniform(0.0008, 0.0030)))
            ticket = m["ticket"] * r.uniform(0.95, 1.05)
            rows.append(dict(
                merchant_id=mid, name=m["name"], vertical=m["vertical"], month=MONTHS[t],
                visa_cnp_sales_count=m["visa_sales"][t],
                visa_tc40_fraud=fraud, visa_tc15_disputes=disputes,
                mc_sales_count=mc_sales, mc_chargebacks=cb, mc_fraud_count=mc_fraud,
                mc_fraud_dollars=int(round(mc_fraud * ticket * r.uniform(0.9, 1.1))),
                mc_sales_dollars=int(round(mc_sales * ticket)),
                mc_chargeback_dollars=int(round(cb * ticket * r.uniform(0.9, 1.3))),
            ))
    return pd.DataFrame(rows)


def verify(df: pd.DataFrame) -> dict:
    """Confirm the planted book behaviour. Raises AssertionError if the tuning drifts."""
    last = df[df["month"] == MONTHS[LAST]]
    ev = last["visa_tc40_fraud"] + last["visa_tc15_disputes"]
    sales = last["visa_cnp_sales_count"]
    m6 = last["merchant_id"] == "M006"
    without = ev[~m6].sum() / sales[~m6].sum()
    with_m6 = ev.sum() / sales.sum()
    assert without < CONFIG.visa_acquirer_above_standard <= with_m6, (without, with_m6)
    return {"book_ratio_without_M006": round(float(without), 6),
            "book_ratio_with_M006": round(float(with_m6), 6)}


def main() -> None:
    df = generate()
    checks = verify(df)
    out = ROOT / "data"
    out.mkdir(exist_ok=True)
    df.to_csv(out / "merchant_months.csv", index=False)
    (out / "manifest.json").write_text(json.dumps({
        "seed": SEED, "rows": len(df), "merchants": int(df["merchant_id"].nunique()),
        "months": MONTHS, "baseline_month": MONTHS[0], "synthetic": True, **checks,
    }, indent=2))
    print(f"wrote {len(df)} rows; {checks}")


if __name__ == "__main__":
    main()
