"""Turns the monthly rollup table into portfolio and merchant views using rules.py."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from . import rules
from .config import CONFIG, DATA_PATH, Thresholds


def load_data(path=DATA_PATH) -> pd.DataFrame:
    if not path.exists():  # first run: build the seeded synthetic data
        from scripts.generate_data import main
        main()
    return pd.read_csv(path).sort_values(["merchant_id", "month"]).reset_index(drop=True)


def evaluated_months(df: pd.DataFrame) -> list:
    """All months except the first, which only supplies prior-month sales."""
    return sorted(df["month"].unique())[1:]


def merchant_months(df_m: pd.DataFrame, cfg: Thresholds = CONFIG) -> list:
    """Month-by-month assessment for one merchant (baseline month excluded from output)."""
    rows = df_m.sort_values("month").to_dict("records")
    mc = []
    for i in range(1, len(rows)):
        mc.append(rules.mc_assess(int(rows[i]["mc_chargebacks"]),
                                  int(rows[i - 1]["mc_sales_count"]), cfg))
    programs = rules.ecm_program_states([m["tier"] for m in mc], cfg)

    out = []
    for i, (m, prog) in enumerate(zip(mc, programs), start=1):
        row = rows[i]
        v = rules.visa_assess(int(row["visa_tc40_fraud"]), int(row["visa_tc15_disputes"]),
                              int(row["visa_cnp_sales_count"]), cfg)
        mc_status = m["status"]
        if prog["in_program"]:
            mc_status = rules.BREACH  # stays in the program until 3 clean months pass
        same_month = rules.ratio(m["chargebacks"], int(row["mc_sales_count"]))
        out.append({
            "month": row["month"],
            "visa": v,
            "mc": {**m, "status": mc_status, "in_program": prog["in_program"],
                   "clean_months": prog["clean_months"], "same_month_ratio": same_month,
                   "sales": int(row["mc_sales_count"]),
                   "chargeback_dollars": int(row["mc_chargeback_dollars"]),
                   "fraud_count": int(row["mc_fraud_count"]),
                   "fraud_dollars": int(row["mc_fraud_dollars"])},
            "worst": rules.worst_status(v["status"], mc_status),
        })
    return out


def book_history(df: pd.DataFrame, cfg: Thresholds = CONFIG) -> list:
    g = df.assign(events=df["visa_tc40_fraud"] + df["visa_tc15_disputes"]) \
          .groupby("month")[["events", "visa_cnp_sales_count"]].sum()
    out = []
    for month in evaluated_months(df):
        a = rules.acquirer_assess(int(g.loc[month, "events"]),
                                  int(g.loc[month, "visa_cnp_sales_count"]), cfg)
        out.append({"month": month, **a})
    return out


def portfolio(df: pd.DataFrame, cfg: Thresholds = CONFIG) -> dict:
    history = book_history(df, cfg)
    merchants = []
    for mid, df_m in df.groupby("merchant_id"):
        months = merchant_months(df_m, cfg)
        latest = months[-1]
        merchants.append({
            "id": mid,
            "name": df_m["name"].iloc[0],
            "vertical": df_m["vertical"].iloc[0],
            "visa": latest["visa"],
            "mc": latest["mc"],
            "worst": latest["worst"],
        })
    return {
        "month": history[-1]["month"],
        "months": [h["month"] for h in history],
        "book": history[-1],
        "book_history": history,
        "lines": {"above_standard": cfg.visa_acquirer_above_standard,
                  "excessive": cfg.visa_acquirer_excessive},
        "merchants": merchants,
    }


def merchant_detail(df: pd.DataFrame, merchant_id: str,
                    cfg: Thresholds = CONFIG) -> Optional[dict]:
    df_m = df[df["merchant_id"] == merchant_id]
    if df_m.empty:
        return None
    months = merchant_months(df_m, cfg)
    latest = months[-1]
    return {
        "id": merchant_id,
        "name": df_m["name"].iloc[0],
        "vertical": df_m["vertical"].iloc[0],
        "months": months,
        "latest": latest,
        "what_if": {
            "visa": rules.visa_what_if(latest["visa"]["events"], latest["visa"]["sales"], cfg),
            "mc": rules.mc_what_if(latest["mc"]["chargebacks"], latest["mc"]["sales"], cfg),
        },
        "thresholds": {
            "visa_ratio": cfg.visa_merchant_ratio, "visa_floor": cfg.visa_merchant_floor,
            "mc_ecm_ratio": cfg.mc_ecm_ratio, "mc_ecm_count": cfg.mc_ecm_count,
            "mc_hecm_ratio": cfg.mc_hecm_ratio, "mc_hecm_count": cfg.mc_hecm_count,
        },
    }
