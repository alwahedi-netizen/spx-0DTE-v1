# KNOWLEDGE.md — what the research has learned

Owner (2026-11-07): "Capture learnings from each idea and build a knowledge
base … rate it, so even if the idea fails today it can be shortlisted as
having potential, and later combined with variants into our own proprietary
system." One row per idea lives in `learnings.csv`; this file is the
synthesis. **Every daily run reads this file first and updates it last.**

## Potential rating (0–5) — separate from PASS/FAIL

The verdict asks "does it stand alone?". The potential asks "is it a useful
building block?". `research_bt` suggests a score from measured traits; the
run confirms it with a written reason.

| Points | Earned when |
|---|---|
| +1 conditional edge | strong active Sharpe (≥ 0.5) in some regime, half or 5-year stretch |
| +1 risk reducer | cuts the worst drop ≥ 30% while keeping ≥ 80% of the benchmark's Sharpe |
| +1 diversifier | positive Sharpe with ≤ 0.3 correlation to the benchmark |
| +1 | positive active return overall |
| +1 | positive active return in the recent half (not decayed) |

**Shortlist = potential ≥ 3.** Original ideas (RESEARCH.md §2b) draw their
ingredients from the shortlist first.

## Shortlist (building blocks)

| Potential | Idea | Block | Why it matters |
|---|---|---|---|
| 5 | DD-2026-11-TREND (10-mo SMA / 12-1 trend, all classes) | risk-reducer | Cut the worst drop on almost every asset (S&P −33% vs −55%, Nasdaq −29% vs −83%) |
| 5 | R-2026-10-28-VTSPYL (vol-managed S&P 1.5×) | conditional-edge | Passed the allocation track: same market, better-shaped return |
| 4 | R-2026-10-28-HFEA (55/45 UPRO/TMF) | conditional-edge | Wins 20-year windows; breaks when stocks and bonds fall together |
| 4 | R-2026-10-28-RPARL (risk parity 2×) | diversifier, risk-reducer | +14.3%/yr vs +9.4%, Sharpe 0.78 vs 0.47 over 20-year windows |
| 4 | R-2026-11-07-CORRACC (correlation acceleration) | risk-reducer | A crisis signal: worst drop −34% vs −55% |
| 4 | G-OVN (overnight drift) | conditional-edge | Real effect; needs auction execution (< 0.5bp/side) |
| 3 | R-2026-11-07-BEST6M (best six months) | risk-reducer | Worst drop −36% vs −55% at similar Sharpe |
| 3 | G-GAPFADE (gap fade) | conditional-edge | 94% confidence near miss — try a regime filter |
| 4 | L-2026-11-07-SAFEHAVEN (yen/franc only when S&P below its 10-mo SMA) | conditional-edge, diversifier | A crisis sleeve that is flat (cash) most of the time — crash pays without equity beta |
| 4 | R-2026-11-07-HOPTREND (1/3/12-mo trend book, 12 ETFs, equal risk) | conditional-edge, diversifier | Corr −0.08 to the rest of the book; the classic managed-futures diversifier |
| 4 | L-2026-11-07-CMDTRENDINFL (DBC only above its 10-mo SMA AND TIPS beating Treasuries) | conditional-edge, risk-reducer | Commodities' worst drop −31% vs −76%: inflation regime × trend works as a gate |
| 3 | R-2026-11-07-MAGICSF (Greenblatt quality-value, survivorship-free) | conditional-edge | Cleared ALL world-class gates incl. factor alpha (t 2.8), +14.2%/yr vs +7.6% 2000-24; failed only the 2017-24 held-out window |
| 3 | R-2026-11-07-EOMTSY (Treasuries over the last 3 days of the month) | conditional-edge, risk-reducer | Sharpe 0.73 vs 0.32 with 6% worst drop; best marginal add to the book (+0.10 Sharpe at 10%) |
| 3 | R-2026-11-07-FOMCUSD (short the dollar on FOMC days) | conditional-edge, diversifier | Tiny, uncorrelated (0.16) event edge; adds +0.04 Sharpe to the book |
| 3 | R-2026-11-07-HYTREND (high-yield 200-day trend) | conditional-edge, risk-reducer | Red team: the PASS was stale mutual-fund prices; on HYG it is a modest crash cutter (−14% vs −18%) |
| 3 | L-2026-11-07-CORRSWITCH (risk parity 2× cut to 1× when stock-bond corr > 0) | conditional-edge, risk-reducer | +12.6%/yr vs +7.7%, worst drop −39% vs −55%; held-out lagged |
| 3 | R-2026-11-07-GPROF, R-2026-11-07-XSMOMSF (gross profitability; momentum — honest data) | conditional-edge | Beat SPY on survivorship-free data but are the known factors (no alpha); correlate 0.78 with each other |

## Data unlocked 2026-11-07 — retest status

Sharadar (survivorship-free + point-in-time) is connected. Retested
2026-11-07 on the point-in-time S&P 500 (2000 → vault):
- **G-MOM → R-2026-11-07-XSMOMSF:** +9.1%/yr vs SPY +7.6%, but no alpha
  (momentum loading 0.41, alpha t −1.1). FAIL. The old "pass" really was bias.
- **TRENDVAL → R-2026-11-07-VALMOMSF:** +10.5% vs +7.6%, no alpha, lagged
  2017-24. FAIL.
- **GREENBLATT → R-2026-11-07-MAGICSF:** +14.2% vs +7.6%, every world-class
  gate cleared (alpha t 2.8), held-out 2017-24 lost → FAIL, shortlist 3.
- **Still queued:** insider clusters (I-2026-10-28-INSIDER). The insiders
  table needs a bulk pull, not per-ticker queries.

## Themes learned so far

1. **Crash protection is cheap and repeatable; outperformance is not.** Trend,
   seasonality and correlation signals all cut drawdowns 35–45% but rarely
   beat buy-and-hold on return. → They belong in an *overlay*, not alone.
2. **Leverage done carefully works.** Vol-targeting (1.5×), 55/45 and risk
   parity 2× pass long-horizon tests — but each has a known failure regime
   (fast rebounds; positive stock–bond correlation).
3. **Theme 1 + theme 2 is the obvious proprietary combination:** lever a
   core whose crashes are cut by an overlay — the lower drawdown is what
   pays for the leverage.
4. **Published calendar/event anomalies decay** (January effect gone; pre-FOMC
   faded after 2015). Treat them as filters, not engines.
5. **High-turnover and short-term reversal ideas die on costs** (RSI2, IBS,
   OU, pairs). Real but tiny effects need better execution, not better signals.
6. **Single-stock cross-sectional ideas are data-capped** until survivorship-
   free prices and point-in-time fundamentals are connected.
8. **On honest data, single-stock "anomalies" are mostly the known factors**
   (2026-11-07). Momentum, value×momentum and gross profitability all beat
   SPY on survivorship-free data, but factor regressions explain them. Only
   quality-value (magic formula) showed real alpha, and it lost the 2017-24
   mega-cap era.
   → Stock ideas must now clear the factor-alpha gate, not just beat SPY.
9. **Stale prices manufacture edges** (HYTREND red team). Mutual-fund NAVs
   for high yield (and anything thinly traded) autocorrelate. A daily rule on
   them looks brilliant and vanishes on the ETF.
   → Test credit/illiquid-asset rules on tradeable ETFs. Fund proxies are
     for history only, never for the verdict.
10. **Theme 1 holds in every asset class tested** (crypto, commodities,
    bonds). Trend/vol-managed BTC cut the worst drop −83% → −46% (breakout
    ensemble: −21%), and commodity trend × inflation cut −76% → −31%. But
    none beat buy-and-hold on return. Crash protection is the repeatable
    product.
11. **The best risk-adjusted building blocks tonight are small, uncorrelated
    calendar/event effects in rates and FX** (end-of-month Treasuries, FOMC
    dollar). Alone they fail the t ≥ 3 bar. Together they lift a book's
    Sharpe. → Judge them with portfolio.marginal, not alone.
12. **Harness/data gaps found 2026-11-07** (reported; the scan does not edit
    the harness):
    - mixed 7-day crypto + weekday calendars drop weekend returns from the
      weekday asset;
    - Yahoo FX bars are stamped a day early in UK summer time;
    - `rb.sharadar()` cannot pass the tickers table's `table=` filter;
    - spot FX earns no interest in the harness;
    - no FRED rates/CPI, which blocks 6 FX carry/value ideas;
    - no back-adjusted futures, which blocks curve/roll ideas.
7. **From the options lab** (RETIRED.md): tight condors die in chop; wide
   unprotected put wings are crash bets (PBW); the negative-GEX regime is the
   lab's strongest measured filter (MNG promoted 2026-11-07).

## Combination candidates queued (original research, §2b)

| Family | Ingredients | Hypothesis |
|---|---|---|
| L-TRENDLEV | DD-TREND overlay × VTSPYL / 1.5–2× S&P | Trend cuts the crashes that make leverage dangerous → higher return at the benchmark's drawdown |
| L-CORRSWITCH | CORRACC × RPARL / HFEA | De-risk the levered stock–bond mix when correlations accelerate (the 2022 failure mode) |
| L-SEASONTREND | BEST6M × DD-TREND | Two independent risk filters agreeing → fewer whipsaws than either alone |
| L-GAPREGIME | GAPFADE × volatility/GEX regime | Condition the near-miss reversal on the regime where it worked |
| L-QVTREND | MAGICSF × DD-TREND | Quality-value had alpha but a −57% drop in 2008; a trend overlay should cut that while keeping the alpha |
| L-RATESBOOK | EOMTSY + FOMCUSD + HYTREND(ETF) + SAFEHAVEN | Tonight's book of small uncorrelated rates/FX edges (Sharpe 1.5 at 2.5% vol): size it with risk parity and test it as one sleeve |
| queued by desks | L-VALTREND (FX), L-CORRDUR (bonds), L-GOLDCRISIS / L-CARRYPROXY (commodities), EQTRENDCREDIT / MEDIAN (bonds) | Next scripts in their asset-class queues (5-per-class cap reached tonight) |

**First portfolio book (2026-11-07):**
- **Contents:** the nine series saved tonight, inverse-vol weighted.
- **Stats:** Sharpe 1.51, 3.8%/yr at 2.5% vol, worst drop −3.6%, 2007-2024 common months.
- **Adds value at 10%:** EOMTSY (+0.10), HYTREND (+0.08), FOMCUSD (+0.04).
- **Dilutes the book:** equity momentum and gross profitability (they add equity beta).
- **Still to do:** rebuild the older shortlist's series (DD-TREND, VTSPYL, HFEA, RPARL…) so they join the book.

Each runs under the vault and automatic trial counting (RESEARCH.md §2b).
