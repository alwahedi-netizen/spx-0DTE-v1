"""I-2026-11-21-FXTREND3 — FX trend with 1-, 3- and 12-month signals blended
equally (Hurst, Ooi & Pedersen 2017), on the same nine G10 currencies, the same
carry-inclusive synthetic forwards and the same vol scaling as
R-2026-11-21-FXTSMOM. A sourced VARIANT of that replication.

RUNS ONLY IF R-2026-11-21-FXTSMOM REPLICATED (quality rule 1): the script
recomputes FXTSMOM's replication check (no evaluate call) and stops without
spending a trial if it fails.

SOURCE: Hurst, Ooi & Pedersen, "A Century of Evidence on Trend-Following
Investing", Journal of Portfolio Management 44(1) 2017, 15-29,
https://doi.org/10.3905/jpm.2017.44.1.015 (AQR working paper:
https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing):
equal-weighted 1-, 3- and 12-month time-series momentum across 67 markets incl.
currencies, 1880-2016, positive in every decade and in 8 of the 10 largest
60/40 drawdowns. The source's headline is multi-asset (no FX-only series is
published), so this script cannot replicate it on its own; it inherits the
FX-construction check from FXTSMOM (AQR TSMOM^FX) and is labelled a variant.
VARIES: R-2026-11-21-FXTSMOM (12-month only) — the difference that matters:
12-month trend reacts late at crisis onsets (AQR TSMOM^FX: 2008-09 -9.2%
before 2008-10 +19.8%); the 1- and 3-month legs flip within weeks, which is
where the crisis payoff should come from. Also related to
R-2026-11-07-HOPTREND (the same 1/3/12 blend on 12 multi-asset ETFs,
potential 4, corr -0.08 to the book) — this is its FX-only sleeve on forwards.

HYPOTHESIS (written before any run): blending faster signals makes the FX
trend sleeve more convex in equity crashes than 12-month trend alone, at a
similar or better Sharpe.
COUNTER-HYPOTHESIS (the source's own caveat, on record): trend "may not
perform well in bear markets that occur very rapidly" — 2020-03 and 2025-04
(vault) are such months; 1-month legs also add whipsaw cost in calm years.
PASS CRITERION (pre-registered):
  B. research_bt verdict vs T-bills (§4 + world-class gates). Expected FAIL
     (t >= 3 out of reach for an FX style over 2005-2024, theme 31).
  C. Crisis sleeve, same test as FXTSMOM (development data, overlap months
     2005-01 .. 2024-10): corr with SPY <= 0; mean excess return in SPY's
     worst-decile months > 0 and above the all-month mean; positive in
     >= 60% of them; full-period Sharpe > 0.
  D. Better than FXTSMOM at its job: worst-decile mean >= FXTSMOM's AND
     monthly Sharpe >= FXTSMOM's, both on the same overlap months (FXTSMOM's
     book is re-simulated on the same data for the comparison; it was
     already evaluated). C and D both hold -> FXTREND3 replaces FXTSMOM as the
     FX crisis-sleeve candidate; else FXTSMOM's result stands and the family
     stops (no more lookback mining).
DATA-TIMING: as FXTSMOM — FX-only, signal and trade on the same `=X` bars
(true ~19:00 ET closes after fix 2). At month-end bar i, for each lookback L
the signal reads USD prices at bar i and the month-end L months earlier plus
the OECD rate gap for months m-2 .. m-L-1; vol reads daily excess returns up
to bar i. Weights decided at close i earn close i -> close i+1 on TR_<ccy>.
RULE (fixed before any run):
  * Per currency: s_c = mean over L in (1, 3, 12) of sign(L-month excess
    return) (values -1, -1/3, 1/3, 1).
  * w_c = s_c x (0.10 / sigma_c) / N, sigma_c = FXTSMOM's EWMA-60d vol;
    N >= 4 else T-bills; gross capped at 1.0. Month-end rebalance.
  * Variants: (1, 3, 9), (1, 3, 15), (1, 2, 12), (1, 4, 12).
Benchmark T-bills; asset_class "fx" (2bp); start 2003-12-01. FAMILY
"fx-tsmom": FXTSMOM's 22 honest trials + 1 + 4 variants = 27. Never vault.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location(
    "fxtsmom", Path(__file__).resolve().parent / "R-2026-11-21-FXTSMOM.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)          # defines helpers only; runs nothing

ID = "I-2026-11-21-FXTREND3"
FAMILY = T.FAMILY
TRIALS = 27


def make(lookbacks=(1, 3, 12)):
    st = {}
    lmax = max(lookbacks)

    def weights(i, dates, px):
        if i == 0:                                     # evaluate() re-simulates
            st.clear()
            st.update(w={}, me=[], prev={}, mu={}, var={}, n={})
        for c in T.CCY:                                # daily vol update (bar i)
            x, u = px[T.TR[c]][i], px[T.TR_USD][i]
            if not (x and u):
                continue
            lv = math.log(x / u)
            if c in st["prev"]:
                r = lv - st["prev"][c]
                if c not in st["var"]:
                    st["mu"][c], st["var"][c], st["n"][c] = 0.0, r * r, 1
                else:
                    st["mu"][c] = T.DELTA * st["mu"][c] + (1 - T.DELTA) * r
                    st["var"][c] = T.DELTA * st["var"][c] + (1 - T.DELTA) * (r - st["mu"][c]) ** 2
                    st["n"][c] += 1
            st["prev"][c] = lv
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        st["me"].append({c: T.usd_price(px, c, i) for c in T.CCY})
        me, ym = st["me"], dates[i][:7]
        if len(me) < lmax + 1:
            st["w"] = {}
            return st["w"]
        raw = {}
        for c in T.CCY:
            if st["n"].get(c, 0) < 60:
                continue
            sigs = []
            for L in lookbacks:
                a, b = me[-1][c], me[-1 - L][c]
                cp = T.carry_part(c, ym, L)
                if not (a and b) or cp is None:
                    break
                s = math.log(a / b) + cp
                sigs.append(0.0 if s == 0 else (1.0 if s > 0 else -1.0))
            if len(sigs) < len(lookbacks):
                continue
            vol = math.sqrt(st["var"][c] * 261)
            sbar = sum(sigs) / len(sigs)
            if vol > 0 and sbar:
                raw[c] = sbar * T.LEG_VOL / vol
        if len(raw) < 4:
            st["w"] = {}
            return st["w"]
        w = {c: v / len(raw) for c, v in raw.items()}
        g = sum(abs(v) for v in w.values())
        if g > 1.0:
            w = {c: v / g for c, v in w.items()}
        st["w"] = {T.TR[c]: v for c, v in w.items() if v}
        return st["w"]
    return weights


weights = make((1, 3, 12))
VARIANTS = {"L1-3-9": make((1, 3, 9)), "L1-3-15": make((1, 3, 15)),
            "L1-2-12": make((1, 2, 12)), "L1-4-12": make((1, 4, 12))}


def compare(ours, base):
    """Criterion D on the overlap months both books hold positions."""
    spy = T.us_monthly("SPY")
    months = [m for m in T.active_months(ours) if m in spy and m in base and abs(base[m]) > 1e-9]
    worst = sorted(months, key=lambda m: spy[m])[:max(1, len(months) // 10)]
    wo = sum(ours[m] for m in worst) / len(worst)
    wb = sum(base[m] for m in worst) / len(worst)
    so = T._sharpe_m([ours[m] for m in months])
    sb = T._sharpe_m([base[m] for m in months])
    return {"months": len(months), "worst_decile_mean_pct": round(wo * 100, 3),
            "fxtsmom_worst_decile_mean_pct": round(wb * 100, 3),
            "sharpe_m": round(so, 3), "fxtsmom_sharpe_m": round(sb, 3),
            "corr_with_fxtsmom": round(T._corr([ours[m] for m in months], [base[m] for m in months]), 3),
            "better_D": bool(wo >= wb and so >= sb)}


if __name__ == "__main__":
    base = T.monthly_excess(T.make(12))
    rep = T.replication(base)
    print(json.dumps({"id": ID, "gate_fxtsmom_replication": rep}, indent=1))
    if not rep.get("replicated"):
        print(json.dumps({"id": ID, "verdict": "NOT RUN",
                          "reason": "R-2026-11-21-FXTSMOM did not replicate; variant not tested, no trial spent"}))
        sys.exit(0)
    r = rb.evaluate(ID, weights, T.SYMS, None, start=T.START, asset_class="fx",
                    trials=TRIALS, family=FAMILY, variants=VARIANTS, fetch=T.fetch,
                    notes="VARIANT of R-2026-11-21-FXTSMOM: Hurst-Ooi-Pedersen 2017 1/3/12-month "
                          "FX trend blend, same 9 G10 carry-inclusive forwards, EWMA-60d vol, "
                          "10%/leg/N, gross <= 1, month-end; T-bills bench; crisis-sleeve test")
    ours = T.monthly_excess(weights)
    try:
        r["crisis_sleeve"] = T.crisis_check(ours)
        r["vs_fxtsmom"] = compare(ours, base)
    except Exception as e:                 # noqa: BLE001 — report, never hide
        r["crisis_sleeve"] = {"error": repr(e)}
    print(json.dumps(r, indent=1))
