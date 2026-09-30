from app import rules
from app.config import CONFIG


# ---- Visa VAMP -----------------------------------------------------------

def test_visa_ratio_is_fraud_plus_disputes_over_cnp():
    assert rules.visa_vamp_ratio(300, 1200, 100_000) == 0.015
    assert rules.visa_vamp_ratio(1, 1, 0) is None


def test_visa_breach_needs_ratio_and_floor():
    # exactly on both lines: breach
    a = rules.visa_assess(500, 1000, 100_000)
    assert a["status"] == rules.BREACH and not a["below_floor"]
    # ratio is fine, events above floor: safe
    assert rules.visa_assess(800, 800, 500_000)["status"] == rules.SAFE


def test_visa_over_ratio_below_floor_is_watch_and_labeled():
    a = rules.visa_assess(40, 60, 4_000)  # 2.5% but only 100 events
    assert a["ratio"] == 0.025
    assert a["status"] == rules.WATCH
    assert a["below_floor"] is True


def test_visa_one_event_short_of_floor_is_not_a_breach():
    a = rules.visa_assess(700, 799, 90_000)  # 1,499 events, 1.67%
    assert a["status"] == rules.WATCH and a["below_floor"]


def test_visa_watch_band_is_80_percent_of_line():
    assert rules.visa_assess(0, 119, 10_000)["status"] == rules.SAFE   # 1.19%
    assert rules.visa_assess(0, 120, 10_000)["status"] == rules.WATCH  # 1.20%
    assert rules.visa_assess(0, 149, 10_000)["status"] == rules.WATCH  # 1.49%


def test_acquirer_lines():
    assert rules.acquirer_assess(499, 100_000)["label"] == "WATCH"
    assert rules.acquirer_assess(500, 100_000)["label"] == "ABOVE STANDARD"
    assert rules.acquirer_assess(699, 100_000)["label"] == "ABOVE STANDARD"
    assert rules.acquirer_assess(700, 100_000)["label"] == "EXCESSIVE"
    assert rules.acquirer_assess(100, 100_000)["label"] == "STANDARD"


def test_acquirer_headroom():
    assert rules.acquirer_assess(480, 100_000)["headroom_events"] == 19   # 499 is the last under-line count
    assert rules.acquirer_assess(520, 100_000)["headroom_events"] == -21


# ---- Mastercard ECM / HECM ----------------------------------------------

def test_mc_ratio_uses_prior_month_sales():
    assert rules.mc_ratio(150, 10_000) == 0.015
    assert rules.mc_ratio(150, None) is None
    assert rules.mc_ratio(150, 0) is None


def test_ecm_requires_both_count_and_ratio():
    assert rules.mc_assess(100, 6_666)["tier"] == rules.ECM         # 1.5001%
    assert rules.mc_assess(99, 1_000)["tier"] is None               # ratio 9.9% but count < 100
    assert rules.mc_assess(150, 11_000)["tier"] is None             # count ok, ratio 1.36%


def test_hecm_requires_both_count_and_ratio():
    assert rules.mc_assess(300, 10_000)["tier"] == rules.HECM       # 3.00%
    assert rules.mc_assess(299, 5_000)["tier"] == rules.ECM         # ratio 5.98%, count < 300
    assert rules.mc_assess(300, 15_000)["tier"] == rules.ECM        # count ok, ratio 2.0%


def test_mc_watch_and_near_hecm():
    w = rules.mc_assess(85, 6_000)  # 1.42%, 85 chargebacks: within 80% of both ECM conditions
    assert w["status"] == rules.WATCH and w["tier"] is None
    assert rules.mc_assess(79, 5_000)["status"] == rules.SAFE       # under 80 chargebacks
    n = rules.mc_assess(339, 12_800)                                # 2.65%, 339
    assert n["tier"] == rules.ECM and n["near_hecm"] and n["status"] == rules.BREACH


def test_growth_inflates_ratio_on_prior_sales():
    prior_based = rules.mc_ratio(352, 22_000)
    same_month = rules.ratio(352, 27_000)
    assert prior_based >= CONFIG.mc_ecm_ratio > same_month


def test_ecm_exit_needs_three_consecutive_clean_months():
    tiers = [None, "ECM", None, None, "ECM", None, None, None, None]
    states = rules.ecm_program_states(tiers)
    in_prog = [s["in_program"] for s in states]
    # enters at index 1; two clean months then a relapse resets the count
    assert in_prog[:6] == [False, True, True, True, True, True]
    assert states[5]["clean_months"] == 1 and states[6]["clean_months"] == 2
    # third consecutive clean month (index 7) exits
    assert in_prog[7] is False and in_prog[8] is False


def test_hecm_month_also_enters_program():
    assert rules.ecm_program_states(["HECM", None])[1]["in_program"] is True


# ---- worst status / what-if ---------------------------------------------

def test_worst_status():
    assert rules.worst_status(rules.SAFE, rules.WATCH) == rules.WATCH
    assert rules.worst_status(rules.SAFE, rules.BREACH, rules.WATCH) == rules.BREACH
    assert rules.worst_status(rules.SAFE, rules.SAFE) == rules.SAFE


def test_max_events_below_is_strictly_below_line():
    for base in (1_000, 6_666, 27_000, 114_000):
        n = rules.max_events_below(0.015, base)
        assert n / base < 0.015 <= (n + 1) / base


def test_visa_what_if_brings_merchant_under_line():
    a = rules.visa_assess(800, 1115, 114_000)  # 1,915 events, 1.68%
    w = rules.visa_what_if(a["events"], 114_000)
    assert w["cut"] > 0
    after = w["events_now"] - w["cut"]
    assert rules.visa_assess(0, after, 114_000)["status"] != rules.BREACH


def test_visa_what_if_picks_cheaper_route():
    # at 99,000 sales the ratio route allows 1,484 events; getting under the 1,500 floor (1,499) is cheaper
    w = rules.visa_what_if(1_600, 99_000)
    assert w["cut"] == 101 and "floor" in w["route"]
    # at 120,000 sales the ratio route (1,799) is cheaper than the floor route
    w3 = rules.visa_what_if(1_850, 120_000)
    assert w3["cut"] == 51 and "ratio" in w3["route"]
    w2 = rules.visa_what_if(1_600, 120_000)
    assert w2["cut"] == 0


def test_mc_what_if_measures_against_this_month_sales():
    w = rules.mc_what_if(147, 8_400)
    assert w["ecm"]["target_chargebacks"] == 125      # 125/8400 = 1.488%
    assert w["ecm"]["cut"] == 22
    assert w["hecm"]["cut"] == 0
    # after the cut, next month's assessment is no longer ECM
    assert rules.mc_assess(147 - w["ecm"]["cut"], 8_400)["tier"] is None


def test_what_if_zero_when_already_under():
    assert rules.visa_what_if(50, 20_000)["cut"] == 0
    assert rules.mc_what_if(10, 5_000)["ecm"]["cut"] == 0
