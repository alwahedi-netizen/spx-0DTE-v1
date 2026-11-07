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
| 3 | G-MOM, I-…-TRENDVAL, I-…-GREENBLATT | data-capped | Strong in the literature; retest on survivorship-free data |

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

Each runs under the vault and automatic trial counting (RESEARCH.md §2b).
