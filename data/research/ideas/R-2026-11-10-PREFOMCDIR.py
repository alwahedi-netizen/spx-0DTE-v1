"""R-2026-11-10-PREFOMCDIR — trade the dollar in the direction the fed funds
futures expect, over the two days BEFORE a scheduled FOMC decision.

SOURCE: Nina Karnaukh, "The Dollar Ahead of FOMC Target Rate Changes", Ohio
State Fisher College WP 2018-14 (https://ideas.repec.org/p/ecl/ohidic/2018-14.html ;
PDF https://acfr.aut.ac.nz/__data/assets/pdf_file/0019/190315/DollarAheadFOMC_NinaKarnaukh.pdf
returned 403 — rule taken from the abstract and the Quantpedia / Macrosynergy
summaries https://vvv.quantpedia.com/?p=766 , https://macrosynergy.com/?p=41075):
the fed funds futures spread 3 days before a meeting signals a hike or cut;
the dollar then rises (hike) / falls (cut) over the following two days, before
the announcement. "A simple trading strategy which exploits this
predictability exhibits a 0.93 Sharpe ratio" (1994-2014, 57 trades: 35 long /
22 short USD). The drift is strongest when FX implied volatility is high and is
read as limited investor attention to the futures market.

DIFFERENT FROM the ledger's FOMC rows: R-2026-11-07-FOMCUSD / L-2026-11-09-
FOMCMOVE are an unconditional SHORT-dollar trade on the announcement bar (an
uncertainty premium); R-2026-11-07-PREFOMC is the equity drift. This trade is
directional (long or short USD by the expected policy move), only before
meetings where a move is priced, and exits before the statement.
FAMILY "fx-prefomc-dir" (new) -> trials 5.

RATIONALE (written before any run): if FX investors are slow to price the
expected policy move that money markets already show, the dollar drifts toward
it in the last days before the decision. Our version tests whether that drift
survived the paper's sample (2015-24 out of sample: 2015-18 hikes, 2019 cuts,
2022-23 hikes, 2024 cut).

DATA ALIGNMENT (checked 2026-11-10 on the cache — the lead must know this):
a Yahoo `=X` daily value labelled L is the price at the START of London day L
(about the previous evening's close), NOT day L's close: the SNB unpeg
(2015-01-15 09:30 UTC) shows in USDCHF=X at label 2015-01-16 while FXF moves
on 2015-01-15; the 2015-03-18 FOMC jump shows in EURUSD=X at label 03-19
while FXE moves on 03-18. So in research_bt the weights set at index i earn
the FX move DURING day dates[i]. This script therefore sets its weights at the
indices labelled T-2 and T-1 (earning those two days' moves, before the
statement on T) and uses only information known before T-2 starts.

RULE (fixed before any run):
  * Meetings: the scheduled FOMC decision dates in R-2026-11-07-PREFOMC.py
    (federalreserve.gov list, imported unchanged). T-k = k weekdays before T.
  * Signal, from data known before London day T-2 opens:
      implied  = 100 - ZQ=F (CBOT 30-day fed funds front-month, Yahoo close)
                 at the last ZQ=F date <= T-3;
      effr     = mean of FRED DFF (effective fed funds) over its last 5 values
                 dated <= T-4 (DFF for day d is published on d+1);
      D        = days in T's month; d2 = D - day(T) (days after the decision);
      E (bp)   = (implied - effr) * 100 * D / d2 — the expected change at T.
    Only when T-3 is in the same calendar month as T (the front contract is
    the meeting month) and d2 >= 8; otherwise no trade (the next-month
    contract that Kuttner-style decoding needs is not on Yahoo).
  * Trade: E >= +12.5bp (more than half a 25bp step priced) -> LONG USD vs an
    equal-weight basket of the 9 G10 currencies (spot pairs EUR GBP AUD NZD
    JPY CHF CAD SEK NOK, 1/n each, gross 1) for days T-2 and T-1;
    E <= -12.5bp -> SHORT USD vs the same basket; else T-bills. Exit before T.
  * Variants (threshold +-25% / +-50%): 6.25, 9.375, 15.625, 18.75bp.
Benchmark: T-bills. asset_class="fx" (2bp). Spot pairs (a 2-day hold earns no
material interest). Start 2004-01 (G10 USD pairs on Yahoo from 2003-12; ZQ=F
from 2000-09; AUDUSD from 2006-05, used when present).
DATA SOURCES: Yahoo (pairs, ZQ=F) + FRED fredgraph.csv (DFF), fetched by this
script and cached in data/research/cache/fred_DFF.json (git-ignored).
EXPECTED WEAKNESS (on the record): ~4-8 trades a year in hiking/cutting cycles,
none in 2009-15 / 2020-21 ZIRP; t >= 3 unlikely alone. Late-month meetings
(d2 < 8) are skipped, which drops some well-known moves (e.g. 2004-06-30).
"""
import calendar
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

_spec = importlib.util.spec_from_file_location(
    "prefomc", Path(__file__).resolve().parent / "R-2026-11-07-PREFOMC.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FOMC = sorted(date.fromisoformat(x) for x in _mod.FOMC)

# currency -> (yahoo symbol, sign of the weight that is LONG the currency)
LEGS = {"EUR": ("EURUSD=X", 1), "GBP": ("GBPUSD=X", 1), "AUD": ("AUDUSD=X", 1),
        "NZD": ("NZDUSD=X", 1), "JPY": ("USDJPY=X", -1), "CHF": ("USDCHF=X", -1),
        "CAD": ("USDCAD=X", -1), "SEK": ("USDSEK=X", -1), "NOK": ("USDNOK=X", -1)}
ZQ = "ZQ=F"
SYMS = [s for s, _ in LEGS.values()] + [ZQ]
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="


def fred(sid):
    """FRED series as {date: float}, cached per day (NB 2026-11-10: FRED
    tarpits unknown User-Agents such as 'Mozilla/5.0' or 'research_bt/1.0';
    the default Python-urllib agent and curl's agent are served)."""
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
        except Exception as e:          # noqa: BLE001 — retry with the other agent
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


def _wd(d, k):
    """k weekdays before date d."""
    x = d
    for _ in range(k):
        x -= timedelta(days=1)
        while x.weekday() >= 5:
            x -= timedelta(days=1)
    return x


def plan():
    """meeting -> (signal day T-3, effr cut-off T-4, hold days {T-2, T-1}),
    only for meetings whose front ZQ contract is the meeting month."""
    out = {}
    for t in FOMC:
        s3, s4 = _wd(t, 3), _wd(t, 4)
        dim = calendar.monthrange(t.year, t.month)[1]
        d2 = dim - t.day
        if s3.month != t.month or s3.year != t.year or d2 < 8:
            continue
        out[t] = (s3.isoformat(), s4.isoformat(), {_wd(t, 2).isoformat(), _wd(t, 1).isoformat()},
                  dim / d2)
    return out


PLAN = plan()
HOLD = {h: t for t, p in PLAN.items() for h in p[2]}


def make(threshold_bp=12.5, dff=None):
    dff = dff if dff is not None else fred("DFF")
    dff_dates = sorted(dff)
    st = {"zq": [], "sig": {}}

    def effr(cutoff):
        # mean of the last 5 DFF values dated <= cutoff
        import bisect
        k = bisect.bisect_right(dff_dates, cutoff)
        xs = [dff[d] for d in dff_dates[max(0, k - 5):k]]
        return sum(xs) / len(xs) if xs else None

    def weights(i, dates, px):
        if i == 0:
            st.update(zq=[], sig={})                 # evaluate() re-simulates: start clean
        z = px[ZQ][i]
        if z:
            st["zq"].append((dates[i], z))
        t = HOLD.get(dates[i])
        if t is None:
            return {}
        if t not in st["sig"]:
            s3, s4, _, scale = PLAN[t]
            zq = [v for d, v in st["zq"] if d <= s3 and d < dates[i]]
            e = effr(s4)
            if not zq or e is None:
                st["sig"][t] = 0
            else:
                exp_bp = ((100.0 - zq[-1]) - e) * 100.0 * scale
                st["sig"][t] = 1 if exp_bp >= threshold_bp else (-1 if exp_bp <= -threshold_bp else 0)
        sg_usd = st["sig"][t]                          # +1 long USD, -1 short USD
        if not sg_usd:
            return {}
        live = [(s, sg) for s, sg in LEGS.values() if px[s][i]]
        if not live:
            return {}
        return {s: -sg_usd * sg / len(live) for s, sg in live}
    return weights


weights = make(12.5)

if __name__ == "__main__":
    r = rb.evaluate("R-2026-11-10-PREFOMCDIR", weights, SYMS, None, start="2004-01-01",
                    asset_class="fx", trials=5, family="fx-prefomc-dir",
                    variants={"TH6": make(6.25), "TH9": make(9.375), "TH16": make(15.625),
                              "TH19": make(18.75)},
                    notes="Karnaukh 2018: long (short) USD vs equal-weight G10 spot basket over days T-2 and "
                          "T-1 before scheduled FOMC decisions when ZQ=F front-month minus 5-day mean DFF, "
                          "scaled to the post-meeting days, prices a hike (cut) of >= 12.5bp; else T-bills. "
                          "Yahoo =X value labelled L = start of London day L (weights at T-2, T-1 earn those days)")
    print(json.dumps(r, indent=1))
