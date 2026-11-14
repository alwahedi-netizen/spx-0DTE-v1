"""R-2026-11-14-MACROANN — the bond risk premium is earned on macro
announcement days (Jones, Lamont & Lumsdaine, "Macroeconomic news and
bond market volatility", JFE 47(3) 1998). Scripts I-2026-11-08-MACROANN
(rejected 2026-11-08 only for missing exact release dates; ALFRED's
vintage dates for PAYEMS ARE the Employment Situation release dates,
1955+, and are reachable with the default Python user-agent).

SOURCE: https://ideas.repec.org/p/wop/priech/_005.html (doi
10.1016/S0304-405X(97)00047-0). Published headline (Treasuries,
1979-1993): a large risk premium is earned on employment / PPI release
days, while excess returns over T-bills on non-announcement days are
ZERO; announcement-day volatility does not persist.

STEP 1 — REPLICATION (no evaluate call; printed, then gates step 2) on the
source's own period 1979-01..1993-12: daily 10-year par-bond excess
returns from FRED DGS10 (r = y/252 - D*dy + 0.5*C*dy^2, D/C of a 10-year
par bond at the prior day's yield) minus FRED DTB3/252, split into
Employment Situation release days (ALFRED PAYEMS vintage dates) and all
other days. REPLICATION PASSES (fixed before any run) when the
release-day mean excess is > 0 with t >= 2.0 AND the non-release-day
mean excess has |t| < 2.0. Otherwise "harness/data suspect" and step 2
does not run (no trial spent). PPI release dates exist in ALFRED only
from 1996-12, so the replication uses employment days alone.

STEP 2 — ETF TEST (one evaluate call). HYPOTHESIS: the premium for
bearing macro-news risk is still concentrated on jobs-report days; IEF
held only over those days (about 12 a year) and T-bills otherwise has a
higher Sharpe than IEF held all year. Expected weakness (logged before
the run): in the market ~5% of days, so like FOMCTSY it may fail t >= 3
even if real — its use would then be as a book ingredient (theme 11/14).
RULE (fixed before any run): weights at close i = IEF 1.0 if bar i+1 is an
Employment Situation release date, else {} (T-bills).
Benchmark: IEF buy & hold. Costs 3bp. Start 2002-08-01.
Variants (4): EMP+CPI (also CPI release days, ALFRED CPIAUCNS vintages);
EMP+PPI (also PPI days, ALFRED PPIACO vintages, 1996-12+); EMP_PREV (also
the bar before the release); EMP_NEXT (also the bar after the release).
trials = 5 (new family R-2026-11-14-MACROANN; no macro-release-day
script exists. FOMC windows are a different family, L-TSYCAL / FOMCTSY,
and are not traded here; jobs Fridays fall in the first ~8 days of the
month, outside the last-3-days window).
PASS CRITERION (written before any run): research_bt verdict PASS with
every world-class gate (99% vs IEF, held-out win, DSR >= 0.95, t >= 3,
double costs, >= 70% of the 4 neighbours beating IEF).
DATA TIMING: release dates are pre-scheduled (BLS publishes its calendar
a year ahead; the 2013 shutdown re-dating was announced days ahead); the
rule reads only that calendar, never a price or yield on/after the trade
day. The weight decided at close i (the evening before an 08:30 ET
release) earns close i -> close i+1 (the release day). ALFRED vintages
are used only as the list of release dates; FRED yields only in step 1.
Data cached per day in data/research/cache/ (git-ignored).
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-14-MACROANN"
BENCH = "IEF"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
ALFRED = "https://alfred.stlouisfed.org/series/downloaddata?seid="


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fred(sid):
    """FRED series as {date: float}, cached per day (default urllib agent)."""
    f = rb.CACHE / f"fred_{sid}.json"
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == _today():
            return j["v"]
    rows = urllib.request.urlopen(FRED + sid, timeout=60).read().decode().strip().splitlines()[1:]
    v = {}
    for line in rows:
        d, x = line.split(",")[:2]
        if x not in ("", "."):
            v[d] = float(x)
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": _today(), "v": v}))
    return v


def release_dates(sid):
    """ALFRED vintage dates of `sid` (= its release dates), cached per day."""
    f = rb.CACHE / f"alfred_vintages_{sid}.json"
    if f.exists():
        j = json.loads(f.read_text())
        if j.get("asof") == _today():
            return set(j["v"])
    html = urllib.request.urlopen(ALFRED + sid, timeout=90).read().decode("utf8", "ignore")
    k = html.find('id="form_selected_vintage_dates"')
    if k < 0:
        raise RuntimeError(f"ALFRED page layout changed for {sid}")
    block = html[k:html.find("</select>", k)]
    v = sorted(set(re.findall(r'value="(\d{4}-\d{2}-\d{2})"', block)))
    if len(v) < 100:
        raise RuntimeError(f"too few ALFRED vintages for {sid}: {len(v)}")
    rb.CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"asof": _today(), "v": v}))
    return set(v)


def par_dur_conv(y, n=20):
    """Modified duration and convexity of a 10-year semiannual par bond at annual yield y."""
    h = y / 2
    cfs = [(k, y / 2 + (1 if k == n else 0)) for k in range(1, n + 1)]
    pv = [cf / (1 + h) ** k for k, cf in cfs]
    price = sum(pv)
    dmod = sum((k / 2) * v for (k, _), v in zip(cfs, pv)) / price / (1 + h)
    conv = sum(cf * k * (k + 1) / 4 / (1 + h) ** (k + 2) for k, cf in cfs) / price
    return dmod, conv


def _mt(x):
    n = len(x)
    m = sum(x) / n
    sd = (sum((a - m) ** 2 for a in x) / (n - 1)) ** 0.5
    return {"mean_bp": round(1e4 * m, 2), "t": round(m / (sd / n ** 0.5), 2), "n": n}


def replication(lo="1979-01-01", hi="1993-12-31"):
    y, tb = fred("DGS10"), fred("DTB3")
    emp = release_dates("PAYEMS")
    ds = sorted(y)
    on, off, last_tb = [], [], None
    for a, b in zip(ds, ds[1:]):
        last_tb = tb.get(a, last_tb)
        if not (lo <= b <= hi) or last_tb is None:
            continue
        y0, dy = y[a] / 100, (y[b] - y[a]) / 100
        dm, cv = par_dur_conv(y0)
        x = y0 / 252 - dm * dy + 0.5 * cv * dy * dy - last_tb / 100 / 252
        (on if b in emp else off).append(x)
    a, b = _mt(on), _mt(off)
    return {"period": f"{lo}..{hi}", "release_days": a, "other_days": b,
            "paper": "premium on release days, zero excess on other days (1979-1993)",
            "passes": bool(a["mean_bp"] > 0 and a["t"] >= 2.0 and abs(b["t"]) < 2.0)}


def make(extra=(), prev=False, nxt=False):
    cache = {}

    def weights(i, dates, px):
        if "days" not in cache:
            days = set(release_dates("PAYEMS"))
            for sid in extra:
                days |= release_dates(sid)
            cache["days"] = days
        days = cache["days"]
        hit = (i + 1 < len(dates) and dates[i + 1] in days) or \
              (prev and i + 2 < len(dates) and dates[i + 2] in days) or \
              (nxt and dates[i] in days)
        return {BENCH: 1.0} if hit and px[BENCH][i] else {}
    return weights


weights = make()

if __name__ == "__main__":
    rep = replication()
    print(json.dumps({"replication": rep}, indent=1))
    if not rep["passes"]:
        print(json.dumps({"idea": ID, "verdict": "NOT TESTED",
                          "reason": "harness/data suspect: the JLL release-day premium did not "
                                    "replicate on FRED 10-year returns 1979-1993 (pre-registered gate)"},
                         indent=1))
        sys.exit(0)
    emp = sorted(d for d in release_dates("PAYEMS") if "2002-08-01" <= d < rb.VAULT_FROM)
    per_year = {}
    for d in emp:
        per_year[d[:4]] = per_year.get(d[:4], 0) + 1
    print(json.dumps({"employment_release_days_per_year": per_year}))
    r = rb.evaluate(ID, weights, [BENCH], BENCH, start="2002-08-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={"EMP_CPI": make(("CPIAUCNS",)), "EMP_PPI": make(("PPIACO",)),
                              "EMP_PREV": make(prev=True), "EMP_NEXT": make(nxt=True)},
                    notes="IEF only over Employment Situation release days (ALFRED PAYEMS vintage "
                          "dates), T-bills otherwise; bench IEF; 2002-08+; Jones-Lamont-Lumsdaine "
                          "JFE 1998; replication on FRED 1979-1993 passed")
    r["replication"] = rep
    print(json.dumps(r, indent=1))
