"""L-2026-11-07-CORRDUR — lab original queued on 2026-11-07 (scored 71, held
by the 5-script cap): the stock-bond correlation picks bond DURATION.

RATIONALE (ledger row, written 2026-11-07, before any run): the sign of the
stock-bond correlation is the market's own read of the inflation regime
(AQR, "A Changing Stock-Bond Correlation", Brixton-Brooks-Hecht-Ilmanen-
Maloney-McQuinn 2023). Negative correlation = growth-shock regime, in which
long Treasuries hedge and earn their term premium; positive correlation =
inflation/term-premium regime (1970s-90s, 2022), in which long duration
loses. Correlation regimes persist for years, so the trailing sign should
say something about next month. Same signal the stocks desk used to
de-lever risk parity (L-2026-11-07-CORRSWITCH, FAIL but shortlist 3); here
it only chooses between long and intermediate Treasuries.
Known risk: 1986-1999 had positive correlation AND a long-bond bull market.

RULE (fixed before any run; instruments moved from the 2026-11-07 fund
sketch to tradeable ETFs per KNOWLEDGE theme 9, before any run):
  * On the first trading day of each month, from closes up to the PREVIOUS
    close: rho = correlation of the last W = 63 paired daily returns of SPY
    and TLT. rho <= 0 -> hold TLT for the month; rho > 0 -> hold IEF.
    Bought at that day's close.
  * Warm-up (until 63 paired returns exist): IEF.
Benchmark: IEF buy & hold (class benchmark; the idea is long-duration most
of the 2002-2021 negative-correlation era, so also read the result against
TLT's own Sharpe in the notes). Costs 3bp. 2002-07-30+ (TLT/IEF inception).
Variants: W = 42 and 84 days; threshold -0.10 and +0.10.
trials = 10 = 1 + 4 variants + the 5 runs of L-CORRSWITCH, which used the
same stock-bond correlation signal (family "L-CORRDUR").
History-only (not the verdict): VFINX/VUSTX/VFITX 1992+ adds the 1990s
positive-correlation bull market the ETFs never saw.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import research_bt as rb

ID = "L-2026-11-07-CORRDUR"
EQ, LONG, MID = "SPY", "TLT", "IEF"


def _corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sab = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    saa = sum((x - ma) ** 2 for x in a)
    sbb = sum((y - mb) ** 2 for y in b)
    return sab / math.sqrt(saa * sbb) if saa > 0 and sbb > 0 else 0.0


def _paired(px, end, n):
    """Last n paired daily returns of EQ and LONG using closes up to `end`."""
    ra, rb_ = [], []
    k = end
    while k >= 1 and len(ra) < n and end - k < 4 * n:
        a0, a1, b0, b1 = px[EQ][k - 1], px[EQ][k], px[LONG][k - 1], px[LONG][k]
        if a0 and a1 and b0 and b1:
            ra.append(a1 / a0 - 1)
            rb_.append(b1 / b0 - 1)
        k -= 1
    return (ra, rb_) if len(ra) == n else (None, None)


def make(window=63, th=0.0):
    st = {"hold": None}

    def weights(i, dates, px):
        if i == 0:
            st["hold"] = None
            return {MID: 1.0} if px[MID][0] else {}
        if dates[i][:7] != dates[i - 1][:7]:
            a, b = _paired(px, i - 1, window)
            if a is not None:
                st["hold"] = LONG if _corr(a, b) <= th else MID
        h = st["hold"] or MID
        return {h: 1.0} if px[h][i] else {}
    return weights


weights = make(63, 0.0)

if __name__ == "__main__":
    import json
    r = rb.evaluate(ID, weights, [EQ, LONG, MID], MID, start="2002-07-30",
                    asset_class="bonds", trials=10, family="L-CORRDUR",
                    variants={"W42": make(42, 0.0), "W84": make(84, 0.0),
                              "TH-0.1": make(63, -0.10), "TH+0.1": make(63, 0.10)},
                    notes="month-start, from the prior close: 63-day SPY/TLT correlation <= 0 -> TLT, "
                          "> 0 -> IEF; bench IEF; ETFs 2002+")
    print(json.dumps(r, indent=1))
