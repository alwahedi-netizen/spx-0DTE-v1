"""R-2026-11-07-CORRACC — correlation acceleration (Quantpedia, Mesicek,
2026-11-06). Rule fixed before the run: average pairwise 20-day correlation of
the nine SPDR sector ETFs vs their 60-day average; if corr20 > 1.13 x corr60 at
today's close, be OUT of SPY tomorrow (the source's SPY + 1-day short overlay =
flat), else hold SPY. X=1.13 is the source's highlighted overlay value from an
in-sample sweep of 26 values (1.00-1.25) -> trials=26 is the honest count.
Strict bar vs SPY, 5bp, 1999+ (sector ETFs start Dec 1998)."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import research_bt as rb

SECT = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
X = 1.13


def _avg_corr(px, i, n):
    rets = {}
    for s in SECT:
        c = px[s][i - n:i + 1]
        if None in c or len(c) < n + 1:
            return None
        rets[s] = [c[k] / c[k - 1] - 1 for k in range(1, len(c))]
    tot, cnt = 0.0, 0
    for a in range(len(SECT)):
        for b in range(a + 1, len(SECT)):
            x, y = rets[SECT[a]], rets[SECT[b]]
            mx, my = sum(x) / n, sum(y) / n
            sxy = sum((p - mx) * (q - my) for p, q in zip(x, y))
            sxx = sum((p - mx) ** 2 for p in x)
            syy = sum((q - my) ** 2 for q in y)
            if sxx and syy:
                tot += sxy / math.sqrt(sxx * syy)
                cnt += 1
    return tot / cnt if cnt else None


def weights(i, dates, px):
    if i < 61:
        return {"SPY": 1.0}
    c20, c60 = _avg_corr(px, i, 20), _avg_corr(px, i, 60)
    if c20 is None or c60 is None:
        return {"SPY": 1.0}
    return {} if c20 > X * c60 else {"SPY": 1.0}


if __name__ == "__main__":
    import json
    print(json.dumps(rb.evaluate("R-2026-11-07-CORRACC", weights, SECT + ["SPY"], "SPY", start="1999-01-01",
                                 cost_bps=5.0, trials=26,
                                 notes="out of SPY next day when sector corr20 > 1.13 x corr60 (source's in-sample pick of 26); 1999+"), indent=1))
