"""R-2026-11-11-VIXCARRY — G10 carry held only while equity volatility is not
elevated (Brunnermeier, Nagel & Pedersen), on the harness-correct DXY-funded
carry book. Promotes ledger row I-2026-11-07-VIXCARRY (replace that row).

SOURCE: Brunnermeier, Nagel & Pedersen, "Carry Trades and Currency Crashes",
NBER Macroeconomics Annual 23 (2008), 313-347
(https://markus.scholar.princeton.edu/sites/g/files/toruqf2651/files/carry_trades_currency_crashes.pdf):
carry currencies crash when risk appetite falls / funding liquidity dries
up; increases in VIX coincide with carry unwinds and predict lower carry
returns. Supporting 2026 evidence: Filippou, Rapach, Taylor & Zhou (JFQA
2026, "flight to fundamentals" when FX volatility is high) and Banque de
France blog 433 (Feb 2026): carry must be judged against volatility.

RATIONALE (written before any run): the carry premium is compensation for
crash risk that materialises in volatility spikes; stepping aside when
volatility is above its recent norm gives up some premium in calm-but-
nervous months and avoids the unwind months, raising the Sharpe and cutting
the negative skew.

CORE (identical to R-2026-11-11-GOODCARRY's carry_book, all six trusts):
  * At each month-end close of month m: OECD 3-month interbank rates
    (FRED IR3TIB01, month m-2); B = DXY-weighted basket rate (EZ .576 JP .136
    GB .119 CA .091 SE .042 CH .036).
  * Candidates: FXE FXY FXF FXA FXB FXC with a price and rate_k > B + 0.40;
    hold the top 2 at 0.25 each + UUP at the same total weight (0.5) =
    long currency k vs the DXY basket, every leg a funded long; rest T-bills.
VIXCARRY RULE: the core is held next month only if the ^VIX close on the
month-end day <= the mean of the last 12 month-end ^VIX closes (incl. this
one); else T-bills. < 12 month-ends seen -> T-bills.
  * Variants (5): M6, M18 (6/18 month-end mean); DVIX (VIX month-end <=
    previous month-end, the source's "VIX not rising" form); NOGATE (the
    ungated core = the control that says whether the gate adds anything).
Benchmark: T-bills (bench None). asset_class="fx" (2bp). Start 2007-03-01.
DATA TIMING: ^VIX, trusts and UUP are all US closes (VIX settles 16:15 ET,
15 minutes after the ETFs - a decision at the same close is the harness
convention and the gap is immaterial for a monthly rule). Rates are read
with a 2-month lag. No Yahoo `=X` series is used (themes 17/21 do not
arise).
FAMILY "fx-carry-dxy" (shared with GOODCARRY: same core). RUN ORDER: after
GOODCARRY -> trials 11 (5 + 6). If run first: trials 6.
DATA SOURCES: Yahoo (trusts, UUP, ^VIX) + FRED fredgraph.csv (9 series),
cached in data/research/cache/fred_<id>.json (git-ignored).
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

TRUSTS = {"FXE": "EZ", "FXY": "JP", "FXF": "CH", "FXA": "AU", "FXB": "GB", "FXC": "CA"}
DXYW = {"EZ": 0.576, "JP": 0.136, "GB": 0.119, "CA": 0.091, "SE": 0.042, "CH": 0.036}
SYMS = list(TRUSTS) + ["UUP", "^VIX"]
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
LAG = 2


def fred(sid):
    """FRED series as {date: float}, cached per day. FRED tarpits unknown
    User-Agents: use the default Python-urllib agent, then curl's."""
    f = rb.CACHE / f"fred_{sid}.json"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == today:
            return j["v"]
    rows, err = None, None
    for hdr in ({}, {"User-Agent": "curl/8.5.0"}):
        try:
            req = urllib.request.Request(FRED + sid, headers=hdr)
            rows = urllib.request.urlopen(req, timeout=30).read().decode().strip().splitlines()[1:]
            break
        except Exception as e:          # noqa: BLE001 - retry with the other agent
            err = e
    if rows is None:
        raise err
    v = {}
    for line in rows:
        d, x = line.split(",")[:2]
        if x not in ("", "."):
            v[d] = float(x)
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": today, "v": v}))
    return v


def load_rates():
    cs = sorted(set(TRUSTS.values()) | set(DXYW))
    return {c: {d[:7]: x for d, x in fred(f"IR3TIB01{c}M156N").items()} for c in cs}


def _month_back(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) - k
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def _rate(series, ym):
    for k in range(7):
        v = series.get(_month_back(ym, k))
        if v is not None:
            return v
    return None


def basket_rate(rates, ym):
    got = {c: _rate(rates[c], ym) for c in DXYW}
    got = {c: r for c, r in got.items() if r is not None}
    tw = sum(DXYW[c] for c in got)
    return sum(DXYW[c] * r for c, r in got.items()) / tw if tw else None


def carry_book(i, px, rates, ym, universe, top_n=2, hurdle=0.40):
    """Target weights of the DXY-funded carry book (same as GOODCARRY's)."""
    b = basket_rate(rates, ym)
    if b is None or not px["UUP"][i]:
        return {}
    cands = []
    for etf in universe:
        r = _rate(rates[TRUSTS[etf]], ym)
        if px[etf][i] and r is not None and r > b + hurdle:
            cands.append((r, etf))
    cands.sort(reverse=True)
    w = {etf: 0.5 / top_n for _, etf in cands[:top_n]}
    if w:
        w["UUP"] = sum(w.values())
    return w


def make(gate="mean", n=12, rates=None):
    """gate: 'mean' (VIX <= mean of last n month-ends), 'dvix' (VIX <= last
    month-end), None (no gate)."""
    rates = rates if rates is not None else load_rates()
    st = {"w": {}, "vix": []}

    def weights(i, dates, px):
        if i == 0:
            st["w"], st["vix"] = {}, []                # evaluate() re-simulates: start clean
        month_end = i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]
        if not month_end:
            return st["w"]
        v = px["^VIX"][i]
        if v:
            st["vix"].append(v)
        on = True
        if gate == "mean":
            hist = st["vix"][-n:]
            on = bool(v) and len(hist) >= n and v <= sum(hist) / n
        elif gate == "dvix":
            on = bool(v) and len(st["vix"]) >= 2 and st["vix"][-1] <= st["vix"][-2]
        st["w"] = carry_book(i, px, rates, _month_back(dates[i][:7], LAG), list(TRUSTS)) if on else {}
        return st["w"]
    return weights


if __name__ == "__main__":
    R = load_rates()
    r = rb.evaluate("R-2026-11-11-VIXCARRY", make(rates=R), SYMS, None, start="2007-03-01",
                    asset_class="fx", trials=26, family="L-fx-etfcarry",
                    variants={"M6": make(n=6, rates=R), "M18": make(n=18, rates=R),
                              "DVIX": make(gate="dvix", rates=R), "NOGATE": make(gate=None, rates=R)},
                    notes="BNP carry with a VIX gate: month-end, DXY-funded carry book (top-2 trusts by "
                          "OECD 3m rate m-2 above the DXY-basket rate + 0.40, 0.25 each + UUP 0.5) held "
                          "only if VIX <= its 12-month-end mean; else T-bills")
    print(json.dumps(r, indent=1))
