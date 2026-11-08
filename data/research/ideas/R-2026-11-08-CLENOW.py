"""R-2026-11-08-CLENOW — Clenow's "Stocks on the Move" on the point-in-time
S&P 500 (survivorship-free).

Promoted from the queue row I-2026-11-07-CLENOW (scored 54 on 2026-11-07).
Varies G-MOM / R-2026-11-07-XSMOMSF: same under-reaction bet, but ranked on
the SMOOTHNESS-adjusted trend (annualised regression slope x R^2), with a
gap filter, a stock-level 100-day trend filter, inverse-volatility sizing and
an index regime filter — the practitioner answer to momentum's crashes.
Source: Clenow (2015) "Stocks on the Move"; point-in-time test by Quanter Lab
(https://quanterlab.com/research/clenow-s-stocks-on-the-move-tested-apart-ten-years-after-the-book),
which already reports 9.5%/yr vs SPY 10.8% over 2006-2025 and a lag every
year since 2015 — expectations are LOW; tested because it was queued and is
cheap to run on our longer survivorship-free sample (1997+, incl. 2000-02).

RATIONALE (fixed before any run): steady (high-R^2) trends reflect gradual,
under-attended information flow (cf. Da-Gurun-Warachka "frog in the pan"),
which persists longer than jumpy trends; the regime filter avoids buying
into bear markets, when momentum is most crash-prone (Daniel-Moskowitz).

RULE (fixed before any run; ledger's monthly simplification of the book's
weekly schedule):
  * Universe: point-in-time S&P 500 members on each month's last close,
    Sharadar survivorship-free prices.
  * Eligible: the last 100 closes all exist; close > 100-day SMA; no daily
    move larger than 15% (absolute) in the last 90 days.
  * Score = (exp(252 x slope) - 1) x R^2 of an OLS fit of ln(close) on time
    over the last 90 closes. Rank eligible stocks by score.
  * Regime: risk-on when SPY closed above its 200-day SMA on each of the
    last 5 trading days.
  * Month end: keep current holdings that are still eligible AND ranked in
    the top 100; if risk-on, add the best-ranked non-held names until 20 are
    held; if risk-off, buy nothing new (freed weight stays in T-bills).
  * Weights: proportional to 1 / (20-day sd of daily returns), scaled so a
    full 20-name book sums to 1 (fewer names -> the rest in T-bills), each
    capped at 15%. Weights drift between month ends.
  * Warm-up (first 200 closes): hold SPY.
  * Variants (robustness gate): hold 15 / 25 names; regression 60 / 120 days.
  * Benchmark SPY, 5bp/side, 1997-01 -> vault, strict bar + FF5+Mom alpha.
  * family "XSMOM" (momentum variant; lifetime count shared with G-MOM/
    XSMOMSF/RESMOM) -> trials passed 15 (5 XSMOMSF + 5 RESMOM + 5 here);
    the harness takes the larger of this and the family's recorded count.
"""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

ID = "R-2026-11-08-CLENOW"
BENCH = "SPY"
_U = {"rows": None, "mem": {}}


def hist():
    if _U["rows"] is None:
        _U["rows"] = rb.sp500_history(first_year=1996)
    return _U["rows"]


def members(day):
    if day not in _U["mem"]:
        _U["mem"][day] = rb.sp500_members(day, hist())
    return _U["mem"][day]


def _score(c, n):
    """(exp(252*slope)-1)*R^2 of ln(close) on time over the last n closes."""
    y = [math.log(v) for v in c[-n:]]
    mx, my = (n - 1) / 2, sum(y) / n
    sxx = sum((k - mx) ** 2 for k in range(n))
    sxy = sum((k - mx) * (v - my) for k, v in enumerate(y))
    syy = sum((v - my) ** 2 for v in y)
    if sxx <= 0 or syy <= 0:
        return None
    slope = sxy / sxx
    r2 = sxy * sxy / (sxx * syy)
    return (math.exp(252 * slope) - 1) * r2


def _sd20(c):
    r = [c[k] / c[k - 1] - 1 for k in range(len(c) - 20, len(c))]
    m = sum(r) / 20
    return (sum((x - m) ** 2 for x in r) / 19) ** 0.5


def make(n_hold=20, reg=90, keep_rank=100, cap=0.15):
    st = {}

    def weights(i, dates, px):
        if i == 0:                                     # fresh state for every simulation
            st.clear()
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if month_end and i >= 205:
            spy = px[BENCH][i - 204:i + 1]
            risk_on = None not in spy and all(
                spy[-1 - k] > sum(spy[-200 - k:len(spy) - k]) / 200 for k in range(5))
            ranked, vol = [], {}
            need = max(100, reg) + 1
            for t in members(dates[i]):
                s = px.get(t)
                if s is None:
                    continue
                c = s[i - need + 1:i + 1]
                if len(c) < need or any(v is None or v <= 0 for v in c):
                    continue
                if c[-1] <= sum(c[-100:]) / 100:
                    continue
                if any(abs(c[k] / c[k - 1] - 1) > 0.15 for k in range(len(c) - 90, len(c))):
                    continue
                sc = _score(c, reg)
                if sc is None:
                    continue
                ranked.append((sc, t))
                vol[t] = _sd20(c)
            ranked.sort(reverse=True)
            top_keep = {t for _, t in ranked[:keep_rank]}
            hold = [t for t in st.get("w", {}) if t in top_keep]
            if risk_on:
                for _, t in ranked:
                    if len(hold) >= n_hold:
                        break
                    if t not in hold:
                        hold.append(t)
            inv = {t: 1.0 / vol[t] for t in hold if vol.get(t)}
            tot = sum(inv.values())
            if tot > 0:
                scale = len(inv) / n_hold
                st["w"] = {t: min(cap, x / tot * scale) for t, x in inv.items()}
            else:
                st["w"] = {}
            st["base"] = {t: px[t][i] for t in st["w"]}
            st["last"] = dict(st["base"])
            return dict(st["w"])
        if "w" not in st:
            return {BENCH: 1.0}                        # warm-up = benchmark
        if not st["w"]:
            return {}
        v = {}
        for t, w in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            v[t] = w * st["last"][t] / st["base"][t]
        # drift: the book's value relative to its start, cash leg unchanged
        w0 = sum(st["w"].values())
        val = sum(v.values()) + (1 - w0)
        return {t: x / val for t, x in v.items()} if val > 0 else {}

    return weights


weights = make()
VARIANTS = {"hold15": make(n_hold=15), "hold25": make(n_hold=25),
            "reg60": make(reg=60), "reg120": make(reg=120)}


if __name__ == "__main__":
    import json
    tickers = sorted({r["ticker"] for r in hist() if r["date"][:10] >= "1996-01-01"}
                     | members("1997-01-02"))
    out = rb.evaluate(ID, weights, tickers, BENCH, start="1997-01-01",
                      asset_class="stocks", source="sharadar", family="XSMOM", trials=15,
                      variants=VARIANTS,
                      notes=("Clenow Stocks on the Move, monthly: (exp(252*slope)-1)*R^2 of 90-day "
                             "log fit, eligible above 100-day SMA and no >15% day in 90; top 20, keep "
                             "while top 100, inverse-vol capped 15%, no new buys unless SPY > 200d SMA "
                             "5 days; point-in-time S&P 500, Sharadar; family XSMOM; promoted from "
                             "I-2026-11-07-CLENOW"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
