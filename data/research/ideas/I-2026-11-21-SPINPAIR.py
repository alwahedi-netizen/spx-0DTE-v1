"""I-2026-11-21-SPINPAIR — spin-offs, the source's own conclusion: hold BOTH the
spun-off subsidiary (22 months) and its parent (15 months), equal weight.

Varies R-2026-11-21-SPINOFF (adds the parent leg; same events, same filters,
same family). SOURCE: McConnell, Sibley & Xu (2015, JPM 42(1) 143-152) —
parents beat their size/market-to-book benchmarks by +3.7% over the first 15
months after the ex date (peak +4.79%), and "a strategy of uniformly
investing in both the parent company and the spun-off subsidiary is the
route to superior investment outcomes".
RATIONALE (fixed before any run): the parent sheds a unit the market
undervalued inside the conglomerate and gets focused management (the same
focus story as the subsidiary), and parents are larger and more liquid, so
the book is less concentrated in small caps than SPINOFF.
RUNS ONLY IF (pre-registered; otherwise prints NOT RUN and spends no test):
  (1) SPINOFF's replication gate is met (recomputed here, deterministic), AND
  (2) results/R-2026-11-21-SPINOFF.json exists with confidence >= 0.90
      (a variant is only worth a trial when the base rule is at least
      PROMISING-grade on confidence).
RULE (fixed before any run):
  * Events and subsidiary leg exactly as R-2026-11-21-SPINOFF (filtered
    Sharadar spin-offs; enter the first priced close within 10 days of the
    ex date; hold 22 months).
  * Parent leg: the ACTIONS `ticker` of each kept event, if its TICKERS row
    is a "Domestic Common Stock" on NYSE/NASDAQ/NYSEMKT/AMEX/BATS/NYSEARCA and
    not a REIT; bought at its first priced close on/after the ex date (within
    10 days), held 15 months; one parent position per (parent, ex date).
    The source also dropped parents acquired at or near the ex date — we
    cannot know that without looking ahead, so an acquired parent simply
    leaves at its last price (5 missing bars), like any delisted name.
  * Equal weight across all live positions (a ticker held twice counts
    once), re-equalised on any entry/exit and at each month's first close.
    No live name -> benchmark.
  * Variants (robustness gate): (sub, parent) holds (22, 12), (22, 19),
    (15, 15), (27, 15).
  * Benchmark MDY, 10bp, 2000-01 -> vault, strict bar + FF5+Mom alpha gate.
    family "spinoffs": trials = SPINOFF's 5 + 1 + 4 = 10.
PASS CRITERION (written before any run): harness verdict PASS vs MDY with
every world-class gate (99% confidence, held-out win with positive return,
DSR >= 0.95 at 10 trials, active t >= 3, 2x costs, >= 70% of variants beat
MDY, FF5+Mom alpha t >= 2).

DATA-TIMING: as SPINOFF — the ex date is public in advance; entry at close i
reads only dates[i], the ex date and whether a price exists at i; exits read
dates[i]. Weights decided at close i earn close i -> close i+1.
"""
import importlib.util
import json
import sys
from pathlib import Path

_here = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location("spinoff_core", _here.with_name("R-2026-11-21-SPINOFF.py"))
so = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(so)
rb = so.rb

ID = "I-2026-11-21-SPINPAIR"
FAMILY = so.FAMILY
TRIALS = 5 + 1 + 4
POS = []          # [(ex_date, ticker, hold_kind)] hold_kind "sub" | "par"


def positions(end=rb.VAULT_FROM):
    subs = so.events(end)
    keep_sub = set(subs)
    meta = so.tickers_meta()
    rows = []
    for y in range(so.EVENTS_FROM, int(end[:4]) + 1):
        rows += rb.sharadar("actions", action="spinoff",
                            **{"date.gte": f"{y}-01-01", "date.lte": f"{y}-12-31"})
    pars = set()
    for r in rows:
        ex, c, p = r["date"][:10], (r.get("contraticker") or "").strip(), (r.get("ticker") or "").strip()
        if (ex, c) not in keep_sub or not p:
            continue
        m = meta.get(p)
        if (not m or not str(m.get("category") or "").startswith("Domestic Common Stock")
                or m.get("exchange") not in so.EXCH or str(m.get("industry") or "").startswith("REIT")):
            continue
        pars.add((ex, p))
    return sorted([(ex, c, "sub") for ex, c in subs] + [(ex, p, "par") for ex, p in pars])


def make_weights(sub_hold=22, par_hold=15):
    st = {}

    def weights(i, dates, px):
        if i == 0:
            st.clear()
            st.update(entry={}, dead=set(), miss={}, w=None, base=None, last=None, live=(), m=None)
        d = dates[i]
        for ex, t, kind in POS:
            key = (ex, t, kind)
            if key in st["entry"] or ex > d or so._days(ex, d) > 10:
                continue
            if t in px and px[t][i] is not None:
                st["entry"][key] = so.add_months(ex, sub_hold if kind == "sub" else par_hold)
        live = set()
        for key, exit_day in st["entry"].items():
            t = key[1]
            if d >= exit_day or key in st["dead"]:
                continue
            if px[t][i] is None:
                st["miss"][key] = st["miss"].get(key, 0) + 1
                if st["miss"][key] >= 5:
                    st["dead"].add(key)
                    continue
            else:
                st["miss"][key] = 0
            live.add(t)
        live = tuple(sorted(live))
        if not live:
            st["w"], st["live"] = None, ()
            return {so.BENCH: 1.0}
        if live != st["live"] or d[:7] != st["m"]:
            priced = [t for t in live if px[t][i] is not None]
            if priced:
                st["w"] = {t: 1.0 / len(priced) for t in priced}
                st["base"] = {t: px[t][i] for t in priced}
                st["last"] = dict(st["base"])
                st["live"], st["m"] = live, d[:7]
                return dict(st["w"])
        if not st["w"]:
            return {so.BENCH: 1.0}
        v = {}
        for t, w0 in st["w"].items():
            p = px[t][i]
            if p is not None:
                st["last"][t] = p
            v[t] = w0 * st["last"][t] / st["base"][t]
        tot = sum(v.values())
        return {t: x / tot for t, x in v.items()} if tot > 0 else {so.BENCH: 1.0}
    return weights


weights = make_weights()
VARIANTS = {"s22p12": make_weights(22, 12), "s22p19": make_weights(22, 19),
            "s15p15": make_weights(15, 15), "s27p15": make_weights(27, 15)}


if __name__ == "__main__":
    so.EVENTS[:] = so.events()
    subs = sorted({c for _, c in so.EVENTS})
    rep = so.replication(subs)
    base = rb.RESULTS / "R-2026-11-21-SPINOFF.json"
    conf = json.loads(base.read_text()).get("confidence") if base.exists() else None
    print("SPINOFF replication", rep["replicated"], rep["excess_pp"], "| SPINOFF confidence", conf)
    if not rep["replicated"] or conf is None or conf < 0.90:
        print(json.dumps({"idea": ID, "verdict": "NOT RUN",
                          "reason": "pre-registered condition not met (SPINOFF replication and confidence >= 0.90)",
                          "spinoff_replicated": rep["replicated"], "spinoff_confidence": conf}))
        sys.exit(0)
    POS[:] = positions()
    tick = sorted({t for _, t, _ in POS})
    print("POSITIONS", len(POS), "tickers", len(tick))
    out = rb.evaluate(
        ID, weights, tick, so.BENCH, start=so.START, asset_class="stocks", cost_bps=so.COST,
        trials=TRIALS, family=FAMILY, variants=VARIANTS, source="sharadar",
        notes=("Spin-off subsidiaries (22m) + parents (15m), equal weight, same filtered Sharadar events as "
               "R-2026-11-21-SPINOFF; acquired parents leave at last price (no look-ahead drop); bench MDY; "
               "10bp; variants (sub,parent) months (22,12) (22,19) (15,15) (27,15); family spinoffs trials 10"))
    print(json.dumps({k: out[k] for k in out if k != "equity"}, indent=1)[:6000])
