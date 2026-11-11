"""R-2026-11-11-BONDCARRYX — Treasury maturity carry: each month hold the
point on the curve with the most carry + roll-down per unit of duration
(Koijen, Moskowitz, Pedersen & Vrugt, "Carry", JFE 127(2) 2018), scripted
from the bond queue (I-2026-11-10-BONDCARRYX), on the FRED H.15 curve.

SOURCES: https://doi.org/10.1016/j.jfineco.2017.11.002 (KMPV "Carry": bond
carry = term spread + roll-down, predicts returns across the curve and
countries; "slope carry" across maturities is one of their strategies);
Brooks, Palhares & Richardson, "Style Investing in Fixed Income", JPM 2018
(https://alphaarchitect.com/2018/05/style-investing-fixed-income/): carry
works for maturity selection in government bonds. Haddad-Kozak-Santosh
(NBER w23886): slope premia are more predictable than level premia.

VARIES: R-2026-11-07-TSCARRY (graveyard; long-vs-bills by the SIGN of one
slope) and R-2026-11-08-MEDIAN (shortlist 4; picks maturities by past
RETURN). This picks a maturity by FORWARD-LOOKING carry per unit of risk.

RATIONALE (written before any run): if expectations of future short rates
are unbiased on average, the bond with the most carry + roll-down per unit
of duration earns the most per unit of rate risk (the term-premium is not
flat across maturities: the curve is usually steepest at the front end,
which is why short maturities often have the best carry/duration — the
low-risk-in-bonds effect, Frazzini-Pedersen BAB). Expected weakness: when
the front end is steep because cuts are coming (2001, 2007-08, 2019-20),
carry points to the short end exactly as long bonds rally; and when the
curve is inverted (2006-07, 2022-24) carry/duration can favour long bonds
that then sell off.

RULE (fixed before any run):
  * Curve: FRED H.15 constant-maturity yields DGS3MO (0.25y), DGS1, DGS2,
    DGS3, DGS5, DGS7, DGS10, DGS20, DGS30 (percent). For each series, the
    latest value DATED STRICTLY BEFORE the previous trading day (data
    timing below); a point whose latest value is more than 10 calendar days
    old (discontinued maturity) or missing is skipped. y(m) = piecewise-linear
    interpolation in maturity over the available points, flat beyond the
    last one (if a long point is missing, e.g. a gap in DGS30 while the
    30-year was suspended, TLT uses DGS20 flat + the 10-20y slope).
  * On the first trading day of each month (weights at that close), for
    each ETF k with a price that day: representative maturity m_k and
    duration D_k: SHY (2y, 1.9), IEI (4.5y, 4.3), IEF (8.5y, 7.5),
    TLT (25y, 17). Expected 1-year carry + roll-down (pp):
        c_k = (y(m_k) - y(0.25)) + D_k x (y(m_k) - y(m_k - 1))
    score_k = c_k / D_k. Hold the top-scoring ETF at 1.0 for the month.
Benchmark: IEF buy & hold. Costs 3bp. Start 2002-08-01 (SHY/IEF/TLT
2002-07; IEI joins the candidates when it lists, 2007-01).
Variants (4): TOP2 (top 2 equal weight); H6 (6-month horizon: 0.5 x
(y(m)-y(0.25)) + D x (y(m) - y(m-0.5))); NOTLT (exclude TLT); RAW (rank c_k,
not c_k / D_k).
trials = 5 (new family; TSCARRY/MEDIAN are different signals with their own
families).
DATA TIMING: H.15 daily yields for date d are posted to FRED on the next
business day (around 4:15pm ET, after the 4pm close). Using only values
dated strictly before dates[i-1] for a trade at close i means every input
was public at least one full session before the trade. H.15 Treasury
yields are not revised after publication (no look-ahead from revisions).
Data: FRED fredgraph.csv with the DEFAULT Python urllib user-agent (cached
per day in data/research/cache/fred_<id>.json, git-ignored).
"""
import bisect
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "R-2026-11-11-BONDCARRYX"
BENCH = "IEF"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
POINTS = {"DGS3MO": 0.25, "DGS1": 1, "DGS2": 2, "DGS3": 3, "DGS5": 5,
          "DGS7": 7, "DGS10": 10, "DGS20": 20, "DGS30": 30}
ETFS = {"SHY": (2.0, 1.9), "IEI": (4.5, 4.3), "IEF": (8.5, 7.5), "TLT": (25.0, 17.0)}


def fred(sid):
    """FRED series as {date: float}, cached per day. Default urllib agent
    (FRED stalls browser-like agents)."""
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


class Series:
    """Point-in-time reader: value of the latest date strictly before a cutoff."""

    def __init__(self, d):
        self.k = sorted(d)
        self.v = [d[x] for x in self.k]

    def before(self, cutoff, max_age=10):
        """None when the latest value is more than max_age calendar days
        older than the cutoff (a discontinued maturity, e.g. DGS30 in
        2002-2006, must drop out, not freeze)."""
        j = bisect.bisect_left(self.k, cutoff) - 1
        if j < 0:
            return None
        age = (datetime.strptime(cutoff, "%Y-%m-%d") - datetime.strptime(self.k[j], "%Y-%m-%d")).days
        return self.v[j] if age <= max_age else None


def load_curve():
    return {mat: Series(fred(sid)) for sid, mat in POINTS.items()}


def curve_at(curve, cutoff):
    pts = sorted((m, s.before(cutoff)) for m, s in curve.items())
    return [(m, y) for m, y in pts if y is not None]


def interp(pts, m):
    if m <= pts[0][0]:
        return pts[0][1]
    for (m0, y0), (m1, y1) in zip(pts, pts[1:]):
        if m <= m1:
            return y0 + (y1 - y0) * (m - m0) / (m1 - m0)
    return pts[-1][1]


def score(pts, mat, dur, horizon=1.0, scaled=True):
    y0 = interp(pts, 0.25)
    ym = interp(pts, mat)
    c = horizon * (ym - y0) + dur * (ym - interp(pts, mat - horizon))
    return c / dur if scaled else c


def make(top=1, horizon=1.0, exclude=(), scaled=True, curve=None):
    st = {}

    def reset():
        st.clear()
        st.update(w={}, curve=curve)

    reset()

    def weights(i, dates, px):
        if i == 0:
            reset()
        if i == 0 or dates[i][:7] == dates[i - 1][:7]:
            return st["w"]
        if st["curve"] is None:
            st["curve"] = load_curve()
        pts = curve_at(st["curve"], dates[i - 1])   # values dated < previous trading day
        if len(pts) < 4 or pts[0][0] != 0.25:
            st["w"] = {BENCH: 1.0} if px[BENCH][i] else {}
            return st["w"]
        cands = sorted(((score(pts, m, d, horizon, scaled), k)
                        for k, (m, d) in ETFS.items()
                        if k not in exclude and px[k][i]), reverse=True)[:top]
        st["w"] = {k: 1.0 / len(cands) for _, k in cands} if cands else {}
        return st["w"]
    return weights


if __name__ == "__main__":
    C = load_curve()
    r = rb.evaluate(ID, make(curve=C), list(ETFS), BENCH, start="2002-08-01",
                    asset_class="bonds", trials=5, family=ID,
                    variants={"TOP2": make(2, curve=C), "H6": make(1, 0.5, curve=C),
                              "NOTLT": make(1, 1.0, ("TLT",), curve=C),
                              "RAW": make(1, 1.0, (), False, curve=C)},
                    notes="first trading day of each month: hold the Treasury ETF (SHY/IEI/IEF/TLT) "
                          "with the highest 1-year carry + roll-down per unit of duration from the "
                          "FRED H.15 curve (values dated before the prior trading day); bench IEF; 2002-08+")
    print(json.dumps(r, indent=1))
