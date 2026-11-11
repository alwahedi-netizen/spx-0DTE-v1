"""L-2026-11-11-ETFROLL — cross-sectional commodity carry measured WITHOUT a
futures curve: the roll yield each futures-based ETF has actually earned,
read as ETF return minus its front-month futures' price change (lab
original, RESEARCH.md §2b, designed 2026-11-11).

VARIES (a fixable data reason, §2b): the curve family is blocked on
contract-level futures (KNOWLEDGE §7 gap c): I-2026-11-07-CMDSLOPE
(WisdomTree, Jan 2026: cross-sectional front roll yield 5.5%/yr, t 3.1,
2001-25), I-2026-11-07-MOMTSDS, I-2026-11-08-BASISMOM, I-2026-11-09-SPOTBASIS
all rejected as untestable. L-2026-11-07-CARRYPROXY (potential 4) proved the
idea works as a TIME-SERIES gate on one market using two USO-family ETFs;
this is the CROSS-SECTIONAL form on seven markets with one ETF each.
SOURCES for the premium: Koijen, Moskowitz, Pedersen & Vrugt, "Carry", JFE
127(2) 2018 (https://econpapers.repec.org/RePEc:eee:jfinec:v:127:y:2018:i:2:p:197-225);
Gorton & Rouwenhorst, "Facts and fantasies about commodity futures", FAJ
2006; Erb & Harvey, FAJ 2006 (roll yield drives long-run commodity
returns); WisdomTree 2026 (above) for a recent out-of-sample confirmation.

THE MEASUREMENT (why it works): Yahoo's continuous front-month series (e.g.
ZC=F) is UNADJUSTED: when it rolls to the next contract its level jumps by
F2 - F1 — up in contango, down in backwardation. An ETF that holds and rolls
the same futures (CORN, USO, ...) earns only the price change of the
contracts it holds plus T-bill interest; it never earns the roll jump. So,
over the same window,
    roll_s = log(ETF_t / ETF_t0) - log(Front_t / Front_t0)
         ~ realised roll yield (+ collateral income, identical across names)
is high (positive) for backwardated markets and low for contango ones.
Collateral income and fees are near-common to all seven ETFs, so the RANK is
the carry rank. (CORN/SOYB/WEAT hold 2nd/3rd/December contracts, USO mostly
the front, UNG the front — so the measure mixes front and deferred slopes;
stated, and the same for every month.)

RATIONALE (written before any run): backwardation signals scarce inventories
(Kaldor-Working storage theory; Gorton-Hayashi-Rouwenhorst 2013) and pays
the long a premium for providing insurance to hedgers; buying the most
backwardated markets is the best-documented cross-sectional commodity
premium. It is a different driver from the desk's demand signals (CCYCMD),
skew, and own-trend.

RULE (fixed before any run):
  pairs (ETF : Yahoo front): CORN:ZC=F SOYB:ZS=F WEAT:ZW=F CANE:SB=F
                             USO:CL=F  UNG:NG=F  CPER:HG=F
  at each month-end close i (date D):
    d1 = date of the last front-month bar dated STRICTLY BEFORE D
    d0 = date of the last front-month bar dated strictly before dates[i-LB]
         (LB = 63 trading days)
    roll_s = log(ETF(d1)/ETF(d0)) - log(F(d1)/F(d0)), ETF values read from the
             simulated calendar at the last date <= d1 / d0 (both < D);
             dropped if any value is missing or |roll_s| > 0.5 (bad tick)
    need >= 5 valid names; hold the 3 HIGHEST roll_s ETFs, 1/3 each, next
    month; else T-bills.
Benchmark: buy & hold DBC. Costs 5bp. Start 2011-09-01 (CANE/SOYB/WEAT
2011-09-19, CPER 2011-11-15; first signal ~2011-12 with 5 names). No 2008
(caveat). Includes 2014-16, 2020 (oil super-contango), 2022 (backwardation).
DATA TIMING: front-month futures are side data loaded on their own calendar
(they trade some US holidays and Sunday evenings; mixing calendars would
add dates — theme 12) and read STRICTLY BEFORE the decision day, so a
futures bar settled after the ETF close can never leak in; the ETF side of
the same window is aligned to those dates. Month-end test peeks dates[i+1]'s
MONTH only.
Variants (neighbours): LB 42 / 126; hold 2 / 4 highest.
NEW FAMILY "L-2026-11-11-ETFROLL": trials 1 + 4 = 5.
Diagnostic printed with the result (no verdict, no trial): per ETF, the mean
annualised roll_s and the share of months held — a red-team check that the
proxy has the known signs (UNG/USO deep contango 2014-20; 2021-22 energy
backwardation).
"""
import bisect
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

PAIRS = {"CORN": "ZC=F", "SOYB": "ZS=F", "WEAT": "ZW=F", "CANE": "SB=F",
         "USO": "CL=F", "UNG": "NG=F", "CPER": "HG=F"}
UNIV = sorted(PAIRS)
START = "2011-09-01"
BAD = 0.5
SIDE = {}          # front symbol -> (sorted dates, closes); filled once, on first use


def _load():
    if not SIDE:
        d, p = rb.prices(sorted(PAIRS.values()), "2009-01-01")
        for s in PAIRS.values():
            pts = [(x, v) for x, v in zip(d, p[s]) if v and v > 0]
            SIDE[s] = ([x for x, _ in pts], [v for _, v in pts])
    return SIDE


def _front_before(f, d):
    ds, vs = _load()[f]
    k = bisect.bisect_left(ds, d)                  # bars dated strictly before d
    return (ds[k - 1], vs[k - 1]) if k > 0 else (None, None)


def _etf_at(px, dates, s, d, i):
    k = bisect.bisect_right(dates, d, 0, i + 1) - 1  # last simulated date <= d (never > i)
    return px[s][k] if k >= 0 else None


def roll_signal(px, dates, i, lb):
    out = {}
    if i < lb:
        return out
    for s, f in PAIRS.items():
        d1, f1 = _front_before(f, dates[i])
        d0, f0 = _front_before(f, dates[i - lb])
        if not (d1 and d0 and f1 and f0) or d0 >= d1:
            continue
        e1, e0 = _etf_at(px, dates, s, d1, i), _etf_at(px, dates, s, d0, i)
        if not (e1 and e0):
            continue
        x = math.log(e1 / e0) - math.log(f1 / f0)
        if abs(x) <= BAD:
            out[s] = x
    return out


def make(lb=63, top=3, min_n=5):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
        if not (i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]):
            return st.get("w", {})
        sig = roll_signal(px, dates, i, lb)
        if len(sig) < max(min_n, top):
            st["w"] = {}
        else:
            pick = sorted(sig, key=lambda s: (-sig[s], s))[:top]
            st["w"] = {s: 1.0 / top for s in pick}
        return st["w"]
    return weights


weights = make()


def proxy_diagnostic(lb=63, top=3):
    """No verdict: mean annualised roll_s per ETF and share of months held."""
    dates, px = rb.prices(UNIV, START)
    keep = sum(1 for d in dates if d < rb.VAULT_FROM)
    dates, px = dates[:keep], {k: v[:keep] for k, v in px.items()}
    sums, cnt, held, months = {}, {}, {}, 0
    for i in range(len(dates) - 1):
        if dates[i + 1][:7] == dates[i][:7]:
            continue
        sig = roll_signal(px, dates, i, lb)
        if len(sig) < 5:
            continue
        months += 1
        for s, x in sig.items():
            sums[s] = sums.get(s, 0.0) + x
            cnt[s] = cnt.get(s, 0) + 1
        for s in sorted(sig, key=lambda s: (-sig[s], s))[:top]:
            held[s] = held.get(s, 0) + 1
    return {"months": months,
            "mean_annual_roll": {s: round(sums[s] / cnt[s] * 252 / lb, 3) for s in sorted(sums)},
            "share_held": {s: round(held.get(s, 0) / months, 2) for s in UNIV} if months else {},
            "note": "diagnostic only - no verdict, no trial"}


if __name__ == "__main__":
    variants = {"lb42": make(42), "lb126": make(126), "top2": make(63, 2), "top4": make(63, 4)}
    res = rb.evaluate("L-2026-11-11-ETFROLL", weights, UNIV, "DBC", start=START,
                      cost_bps=5.0, asset_class="commodities", trials=5,
                      family="L-2026-11-11-ETFROLL", variants=variants,
                      notes="month-end: hold the 3 of CORN/SOYB/WEAT/CANE/USO/UNG/CPER with the highest "
                            "realised roll over 63 days = log ETF return minus log change of its unadjusted "
                            "Yahoo front-month future (front bars strictly before the decision day), 1/3 each, "
                            "else T-bills; bench DBC; lab original (ETF proxy for XS carry, KMPV 2018)")
    res["proxy_diagnostic"] = proxy_diagnostic()
    print(json.dumps(res, indent=1))
