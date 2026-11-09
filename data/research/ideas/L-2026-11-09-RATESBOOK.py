"""L-2026-11-09-RATESBOOK — lab original (RESEARCH.md §2b): KNOWLEDGE.md
combination queue "L-RATESBOOK v2" = TSYCAL + MEDIAN + EQCREDIT + HAVENVOL
held together as ONE risk-parity-sized sleeve. The book itself is tested.

INGREDIENTS (all shortlist potential 4, all FAIL alone on t >= 3 / DSR):
  * L-2026-11-08-TSYCAL   IEF on month-end + FOMC windows, else T-bills
                          (Sharpe 0.92 vs 0.32, best marginal add +0.12)
  * R-2026-11-08-MEDIAN   middle-ranked Treasury ETFs by 6-month return
  * R-2026-11-08-EQCREDIT HYG while the S&P 500 is above its 10-mo SMA, else IEI
  * L-2026-11-08-HAVENVOL FXY+FXF only when global FX volatility is above
                          its trailing 12-month norm, else T-bills
Each sleeve's weights() is IMPORTED unchanged from its own script (importlib,
as L-2026-11-08-QVTREND imports MAGICSF), so the book runs exactly the
pre-registered rules.

RATIONALE (written before any run): KNOWLEDGE themes 11, 14, 15 — small,
uncorrelated rates/FX edges fail t >= 3 alone because each is weak or rarely
invested; four different drivers (calendar flows + policy news; curve mean
reversion; equity-led credit timing; FX-stress haven demand) should add
their excess returns while noise adds in quadrature. Inverse-volatility
sizing stops the most volatile sleeve (credit, FX) from dominating, which is
what made the 2026-11-08 portfolio book (Sharpe 1.56 at 2% vol) work.

RULE (fixed before any run):
  * Every day, each sleeve produces its own target weights (its own rules,
    own state). Book weight of a symbol = sum_k a_k * w_k(symbol).
  * Sleeve budgets a_k are set on the first trading day of each month from
    each sleeve's own daily return stream (from its prior-day weights and
    today's closes; cash = 0 return, immaterial for vol): vol_k = sample
    stdev of the last LOOK = 63 daily returns * sqrt(252), floored at
    FLOOR = 2%/yr (no sleeve is treated as safer than short Treasuries, so a
    sleeve sitting in cash cannot claim an infinite budget); a_k ∝ 1/vol_k,
    normalised to sum 1. Budgets are fixed for the month (the book is re-set
    to target daily; sleeve-internal drift is ignored). Until 63 returns
    exist: a_k = 1/4. No leverage: gross <= 1, the rest earns T-bills.
  * HAVENVOL's FX-volatility signal reads the 9 G10 USD pairs. To avoid the
    harness calendar gap (theme 12: Yahoo FX bars stamped on ~545 summer
    Sundays 2007-24 would put FX-only dates into the union calendar, on
    which held ETFs earn 0 and the weekend move is LOST), the pairs are NOT
    passed to evaluate(). They are loaded separately and aligned onto the
    ETF calendar: on ETF day k the sleeve sees the last FX close stamped
    strictly BEFORE dates[k-1] (a >= 1-day lag that also covers the early
    stamp; immaterial for a monthly vol signal). FXY/FXF themselves are
    normal ETF symbols.
Benchmark: IEF buy & hold. Costs 3bp (bonds; the FX sleeve's 2bp is not
modelled separately). 2006-06+ (EQCREDIT's SMA warm-up; HYG 2007-04;
SHV/TLH 2007-01; HAVENVOL's signal warms ~13 months; sleeves in warm-up hold
what their own scripts hold: IEF / AGG / cash).
Variants: LOOK 42 and 126 days (floor 2%); FLOOR 1% and 4% (LOOK 63).
trials = 45 = own 5 + every ingredient run the book was chosen from:
TSYCAL 15 (incl. EOMTSY 5 + FOMCTSY 5), MEDIAN 5, EQCREDIT 5,
L-fx-safehaven 15. Family "L-RATESBOOK".
Check after the run: portfolio.marginal vs the shortlist book (it overlaps
the book by construction, so the stand-alone gates are the test).
"""
import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "L-2026-11-09-RATESBOOK"
HERE = Path(__file__).resolve().parent
BENCH = "IEF"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tsycal = _load("tsycal", "L-2026-11-08-TSYCAL.py")
median = _load("median", "R-2026-11-08-MEDIAN.py")
eqcredit = _load("eqcredit", "R-2026-11-08-EQCREDIT.py")
havenvol = _load("havenvol", "L-2026-11-08-HAVENVOL.py")

PAIRS = list(havenvol.PAIRS)
ETFS = sorted({tsycal.SYM, *median.UNIV, median.BENCH, eqcredit.SIG, eqcredit.RISK,
               eqcredit.SAFE, eqcredit.BENCH, *havenvol.HAVENS})


def _fx_default(symbols, start):
    return rb.prices(symbols, start)


FX_LOADER = _fx_default          # smoke tests swap in synthetic FX data


def align_fx(dates, fx_dates, fx_px):
    """FX close per ETF day k = last FX close stamped strictly before
    dates[k-1] (None for k = 0 or when none exists)."""
    out = {p: [None] * len(dates) for p in PAIRS}
    j, last = 0, {p: None for p in PAIRS}
    for k in range(1, len(dates)):
        cut = dates[k - 1]
        while j < len(fx_dates) and fx_dates[j] < cut:
            for p in PAIRS:
                v = fx_px[p][j]
                if v:
                    last[p] = v
            j += 1
        for p in PAIRS:
            out[p][k] = last[p]
    return out


class _FXView:
    """px view for HAVENVOL: lagged, aligned pairs + the real FXY/FXF columns."""

    def __init__(self, fx_cols, clock):
        self.fx = {p: rb._Past(c, clock) for p, c in fx_cols.items()}
        self.px = None

    def __getitem__(self, sym):
        return self.fx[sym] if sym in self.fx else self.px[sym]


def _sd(x):
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def make(look=63, floor=0.02):
    st = {}

    def reset(dates):
        st.clear()
        st["sleeves"] = [("TSYCAL", tsycal.make(3, (-1, 0, 1))),
                         ("MEDIAN", median.make(6)),
                         ("EQCREDIT", eqcredit.make(10)),
                         ("HAVENVOL", havenvol.make(12))]
        n = len(st["sleeves"])
        st["a"] = [1.0 / n] * n
        st["prev"] = [{} for _ in range(n)]
        st["hist"] = [[] for _ in range(n)]
        st["clock"] = [0]
        fx_dates, fx_px = FX_LOADER(PAIRS, "2005-01-01")
        st["fxview"] = _FXView(align_fx(dates, fx_dates, fx_px), st["clock"])

    def weights(i, dates, px):
        if i == 0:
            reset(dates)
        st["clock"][0] = i
        st["fxview"].px = px
        n = len(st["sleeves"])
        if i > 0:
            for k in range(n):                       # sleeve return i-1 -> i
                r = 0.0
                for s, w in st["prev"][k].items():
                    a, b = px[s][i - 1], px[s][i]
                    if a and b:
                        r += w * (b / a - 1)
                st["hist"][k].append(r)
            if dates[i][:7] != dates[i - 1][:7] and len(st["hist"][0]) >= look:
                inv = [1.0 / max(_sd(h[-look:]) * math.sqrt(252), floor) for h in st["hist"]]
                tot = sum(inv)
                st["a"] = [v / tot for v in inv]
        book = {}
        for k, (name, fn) in enumerate(st["sleeves"]):
            view = st["fxview"] if name == "HAVENVOL" else px
            w = fn(i, dates, view) or {}
            st["prev"][k] = dict(w)
            for s, v in w.items():
                if v:
                    book[s] = book.get(s, 0.0) + st["a"][k] * v
        return book
    return weights


weights = make(63, 0.02)

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, ETFS, BENCH, start="2006-06-01",
                    asset_class="bonds", trials=45, family="L-RATESBOOK",
                    variants={"LOOK42": make(42, 0.02), "LOOK126": make(126, 0.02),
                              "FLOOR1": make(63, 0.01), "FLOOR4": make(63, 0.04)},
                    notes="risk-parity book of 4 shortlist sleeves (TSYCAL, MEDIAN, EQCREDIT, "
                          "HAVENVOL; each imported unchanged), inverse 63-day sleeve vol floored at "
                          "2%/yr, monthly budgets, no leverage; FX pairs aligned off-calendar "
                          "(1-day lag) to avoid the FX-Sunday gap; bench IEF; 2006-06+")
    print(json.dumps(r, indent=1))
