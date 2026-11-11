"""R-2026-11-11-CYCLEFAC — Treasury yield cycle vs trend inflation sets
duration (Cieslak & Povala, "Expected Returns in Treasury Bonds", RFS 28(10)
2015), real-time ETF version on FRED data.

SOURCES: https://ideas.repec.org/a/oup/rfinst/v28y2015i10p2859-2901..html
(NBER conference draft https://www.nber.org/confer/2011/APs11/CieslakPovala_Premia_Apr2011.pdf);
NY Fed SR 884 (https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr884.pdf)
replicates that trend inflation (not r*) predicts bond returns; Swedroe
summary https://www.etf.com/sections/index-investor-corner/swedroe-cycle-factor-can-predict-returns ;
Brooks-Palhares-Richardson (JPM 2018) define bond VALUE the same way
(yield minus maturity-matched expected inflation).
Finding (1971-2011): split yields into a slow trend-inflation component
tau (a discounted moving average of past core CPI inflation, v = 0.987/month,
N = 120 months) and "cycles" c_n = y_n - tau. Cycles forecast annual bond
excess returns (R2 up to ~50% in-sample, ~30% out-of-sample); yields high
relative to trend inflation mean high expected bond returns.

VARIES: I-2026-11-07-NFVALUE (rejected: needed SPF inflation forecasts).
Trend core CPI replaces SPF, which is the paper's own real-time
expectations proxy, so the data block is gone. Not CPFACTOR (forward
rates, rejected) and not TSCARRY/FFTERM (slope): the signal is the LEVEL
of the 10y yield net of trend inflation, i.e. bond value.

RATIONALE (written before any run): investors' inflation expectations move
slowly with realised core inflation; the part of the 10-year yield above
that trend is the real-rate + term-premium cycle, which mean-reverts within
a few years (CP: cycles are the least persistent yield component). When
the cycle is high relative to its own recent history, bonds are cheap and
should earn more; when low (yields squeezed below trend inflation, as in
2020-21), duration is expensive. Expected weakness: a single 10y cycle
without CP's cross-maturity regression is cruder than the paper's factor
(the regression would be look-ahead unless estimated recursively), and a
"cheap" bond can get cheaper in a hiking cycle (2022).

RULE (fixed before any run):
  * Core inflation pi_t = ln(CPILFENS_t / CPILFENS_{t-12}) (FRED, CPI-U
    core, NOT seasonally adjusted — NSA CPI is never revised, and the
    12-month change removes seasonality). Trend tau_t = sum_{j=0..119}
    v^j pi_{t-j} / sum v^j, v = 0.987 (CP's values).
  * On the first trading day of month M (weights at that close): tau from
    CPI months up to M-2 (month M-1's CPI is released mid-month M — not yet
    public). y10 = FRED DGS10, latest value dated strictly before the
    previous trading day. cycle = y10 - tau.
  * History: the same cycle computed at each of the last WIN = 120 prior
    month-starts (each with its own point-in-time CPI and DGS10). If
    cycle > median(history) -> IEF 1.0 for the month, else SHY 1.0.
Benchmark: IEF buy & hold. Costs 3bp. Start 2002-08-01 (IEF/SHY 2002-07;
FRED history from 1962 so the 120-month window is full from the start).
Variants (4): v = 0.98 and 0.99 (faster/slower trend); WIN = 60 and 240.
trials = 5 (new family; NFVALUE was never run).
DATA TIMING: CPILFENS month m is published mid m+1, so month M uses m <= M-2
(a full extra month of safety around release dates); DGS10 for date d is
posted the next business day after the close, so only values dated before
dates[i-1] are used for a trade at close i. Neither series is revised.
FRED fredgraph.csv with the DEFAULT Python urllib user-agent, cached per day
in data/research/cache/fred_<id>.json (git-ignored).
"""
import bisect
import json
import math
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-11-CYCLEFAC"
BENCH, SHORT = "IEF", "SHY"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="


def fred(sid):
    """FRED series as {date: float}, cached per day (default urllib agent)."""
    f = rb.CACHE / f"fred_{sid}.json"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == today:
            return j["v"]
    rows = urllib.request.urlopen(FRED + sid, timeout=60).read().decode().strip().splitlines()[1:]
    v = {}
    for line in rows:
        d, x = line.split(",")[:2]
        if x not in ("", "."):
            v[d] = float(x)
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": today, "v": v}))
    return v


def _ym_back(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) - k
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def load():
    cpi = {d[:7]: x for d, x in fred("CPILFENS").items()}
    d10 = fred("DGS10")
    keys = sorted(d10)
    return {"cpi": cpi, "k": keys, "v": [d10[x] for x in keys]}


def tau(data, ym_last, v):
    """Trend core inflation (pp) from CPI months <= ym_last."""
    num = den = 0.0
    for j in range(120):
        a = data["cpi"].get(_ym_back(ym_last, j))
        b = data["cpi"].get(_ym_back(ym_last, j + 12))
        if a is None or b is None:
            return None
        w = v ** j
        num += w * 100 * math.log(a / b)
        den += w
    return num / den


def y10_before(data, cutoff):
    j = bisect.bisect_left(data["k"], cutoff) - 1
    return data["v"][j] if j >= 0 else None


def cycle_at(data, ym, cutoff, v):
    """Cycle known on the first trading day of month ym (cutoff = previous
    trading day, as 'YYYY-MM-DD'; values dated strictly before it)."""
    t = tau(data, _ym_back(ym, 2), v)
    y = y10_before(data, cutoff)
    return None if t is None or y is None else y - t


def make(v=0.987, win=120, data=None):
    st = {}
    memo = {}

    def reset():
        st.clear()
        st.update(w={}, data=data)
        memo.clear()

    reset()

    def hist_cycle(ym):
        # a PAST month-start (always before the decision month): DGS10 dated
        # before the 1st of that month, CPI to that month - 2 (pure function
        # of the data, memoised)
        key = (ym, v)
        if key not in memo:
            memo[key] = cycle_at(st["data"], ym, ym + "-01", v)
        return memo[key]

    def weights(i, dates, px):
        if i == 0:
            reset()
        if i == 0 or dates[i][:7] == dates[i - 1][:7]:
            return st["w"]
        if st["data"] is None:
            st["data"] = load()
        ym = dates[i][:7]
        now = cycle_at(st["data"], ym, dates[i - 1], v)
        hist = [hist_cycle(_ym_back(ym, k)) for k in range(1, win + 1)]
        hist = [h for h in hist if h is not None]
        if now is None or len(hist) < int(0.9 * win):
            st["w"] = {BENCH: 1.0} if px[BENCH][i] else {}
            return st["w"]
        sym = BENCH if now > statistics.median(hist) else SHORT
        st["w"] = {sym: 1.0} if px[sym][i] else {}
        return st["w"]
    return weights


if __name__ == "__main__":
    D = load()
    r = rb.evaluate(ID, make(data=D), [BENCH, SHORT], BENCH, start="2002-08-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={"V980": make(0.98, 120, D), "V990": make(0.99, 120, D),
                              "WIN60": make(0.987, 60, D), "WIN240": make(0.987, 240, D)},
                    notes="first trading day of each month: cycle = DGS10 - trend core inflation "
                          "(CPILFENS 12m log change, discounted avg v=0.987 over 120 months, CPI to "
                          "month M-2); IEF if cycle > median of its last 120 month-start values, "
                          "else SHY; bench IEF; 2002-08+; Cieslak-Povala RFS 2015")
    print(json.dumps(r, indent=1))
