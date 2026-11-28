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
| 0 | ~~R-2026-11-07-FOMCUSD~~ | — | **WITHDRAWN 2026-11-10:** Yahoo `=X` values are start-of-day prices, so it measured the day BEFORE each FOMC decision; removed from the book (series moved to series_withdrawn/) |
| 4 | R-2026-11-14-CORRMOMREV (commodity correlation-switched momentum/reversal, long/short DB sectors) | diversifier, conditional-edge | League round 1: 99.86%, fails only t >= 3; corr 0.03 to the book, +0.14 book Sharpe at 10%; fitted setting (honest Sharpe ~0.4); round 2: independent 10-ETF check PARTIAL (beats both legs, Sharpe 0.11) — stays 4, vault allowed |
| 3 | L-2026-11-21-EOMCREDIT (LQD over the last 3 days of the month) | risk-reducer, diversifier | Fails alone (conf 66%) but +0.12 book Sharpe at 10%, worst drop −12% vs −18% (AGG) |
| 3 | O-2026-11-21-LOCKOUTOOS / MIIL (no new MEIC side after a same-side stop) | conditional-edge | Saved $2.7k in the −9% week, matches the MIIL paper lane; trend-day effect only so far — re-judge after 10+ range days |
| 4 | L-2026-11-14-STKBOOK (4 point-in-time stock sleeves) | conditional-edge | League round 1: fails only deflated Sharpe 0.947; alpha ~3%/yr t 3.4 net of the equal-weight tilt; lowers the book Sharpe (corr 0.63) |
| 3 | R-2026-11-07-HYTREND (high-yield 200-day trend) | conditional-edge, risk-reducer | Red team: the PASS was stale mutual-fund prices; on HYG it is a modest crash cutter (−14% vs −18%) |
| 3 | L-2026-11-07-CORRSWITCH (risk parity 2× cut to 1× when stock-bond corr > 0) | conditional-edge, risk-reducer | +12.6%/yr vs +7.7%, worst drop −39% vs −55%; held-out lagged |
| 3 | R-2026-11-07-GPROF, R-2026-11-07-XSMOMSF (gross profitability; momentum — honest data) | conditional-edge | Beat SPY on survivorship-free data but are the known factors (no alpha); correlate 0.78 with each other |
| 4 | L-2026-11-08-TSYCAL (IEF over the last 3 days of the month OR the 3 days around FOMC, else T-bills) | conditional-edge, risk-reducer | Sharpe 0.92 vs 0.32, worst drop −5% vs −24%, held-out 1.07 vs −0.16, confidence 99.7%; best marginal add to the book (+0.12); fails only DSR/t (too few trading days) |
| 4 | L-2026-11-07-CARRYPROXY (USO only when its 3-month return beats USL's, else T-bills) | conditional-edge, risk-reducer | +5.5%/yr vs −11.4% (USO), worst drop −45% vs −98%; ETF proxy for oil curve carry |
| 3 | R-2026-11-08-CMDSKEW (3 lowest-skew of 10 commodity ETFs) | conditional-edge | +4.6%/yr vs −1.5% (DBC), confidence 92%; **caveat 2026-11-10:** an independent replication finds the premium only in agriculturals — an ag-only version is the next test |
| 4 | R-2026-11-08-EQCREDIT (HYG while S&P above its 10-mo SMA, else IEI) | conditional-edge, risk-reducer | Sharpe 0.50 vs 0.34 (AGG) on tradeable ETFs |
| 4 | R-2026-11-08-MEDIAN (middle-ranked Treasury ETFs by 6-month return) | conditional-edge, risk-reducer | Sharpe 0.44 vs 0.30, worst drop −16% vs −24%; adds +0.03 to the book |
| 3 | L-2026-11-08-HAVENRATES (yen+franc only in falling-yield bears) | diversifier | Flat most of the time; unchanged by the harness fix. **HAVENVOL dropped to 3→ weak:** after the FX-date fix it earns ~T-bills (Sharpe 0.03, worst drop −29%); the bug had flattered it |
| 3 | R-2026-11-08-FOMCTSY (IEF only around FOMC decisions) | conditional-edge, risk-reducer | Held-out 0.87 vs −0.16; adds +0.07 to the book; strongest as part of TSYCAL |
| 3 | R-2026-11-08-ASSETGROW (lowest asset growth, point-in-time S&P 500) | conditional-edge | +10.9%/yr vs +8.7%, beat SPY in the held-out window; no factor alpha (t 0.6 — it is the CMA factor) |
| 3 | R-2026-11-08-CLENOW (Clenow momentum with a market filter) | conditional-edge, risk-reducer | +11.6%/yr vs +8.7%, worst drop −27% vs −55%; alpha t 1.4 |
| 3 | L-2026-11-07-CORRDUR (TLT/IEF by stock-bond correlation) | conditional-edge | Worked before 2018, lost after; keep only as a correlation-regime ingredient |
| 4 | L-2026-11-08-OILCURVETREND (USO only when curve-tight AND above trend) | conditional-edge, risk-reducer, diversifier | +5.7%/yr vs −9.3% (USO), worst drop −28% vs −98%, confidence 96%, corr 0.12 to the book |
| 4 | R-2026-11-09-CCYCMD (commodity currencies predict commodities, Chen-Rogoff-Rossi) | conditional-edge, diversifier | +4.7%/yr vs +0.6% (DBC), worst drop −35% vs −76%, corr 0.15 to the book; **2026-11-28 =X fix: 4.9%/yr, conf 92%, worst drop −30%; round 3 CCYDEMAND shows its edge is mostly the dollar** |
| 3 | L-2026-11-08-POLICYMOM (Treasuries by Fed policy direction) | risk-reducer | Sharpe 0.37 vs 0.32, worst drop −14% vs −24% |
| 0 | ~~L-2026-11-09-FOMCMOVE~~ | — | **WITHDRAWN 2026-11-10:** same start-of-day `=X` dating error as FOMCUSD |
| 4 | L-2026-11-09-CMDBOOK (OILCURVETREND + CCYCMD + CARRYPROXY + CMDSKEW, inverse-vol) | conditional-edge, risk-reducer, diversifier | +6.9%/yr vs +0.1% (DBC), worst drop −28% vs −76%, **99.4% confidence, held-out win**; failed only DSR/t. The best commodity block |
| 3 | L-2026-11-10-RATESLEV (RATESBOOK v2 levered to IEF's vol, +50bp financing) | conditional-edge | +6.5%/yr vs +3.4% (IEF) at the same worst drop (−24%), **99.3% confidence**; held-out lost money (less than IEF) |
| 3 | R-2026-11-10-RND (R&D intensity, point-in-time S&P 500) | conditional-edge | +12.8%/yr vs +7.6%, factor alpha t 2.7, held-out win; confidence 94%. Best book add tonight (+0.09) |
| 3 | L-2026-11-10-CCYCURVE (oil curve gated by commodity currencies) | diversifier | +3.0%/yr vs −11.4% (USO), corr 0.09 to the book |
| 3 | R-2026-11-09-NETISS, R-2026-11-09-ACCRUALS (share issuance; accruals — survivorship-free) | conditional-edge | NETISS +11.5%/yr vs +7.6%, 99.8% confidence, held-out win; both are known factors (alpha t 1.0 / 1.5) |
| — | HAVENBASKET, HAVENVOTE (variants of the yen/franc crisis sleeve) | diversifier | Same family as HAVENVOL (now 26+ trials); kept under the HAVENVOL row, not new entries |

## Data unlocked 2026-11-07 — retest status

Sharadar (survivorship-free + point-in-time) is connected. Retested
2026-11-07 on the point-in-time S&P 500 (2000 → vault):
- **G-MOM → R-2026-11-07-XSMOMSF:** +9.1%/yr vs SPY +7.6%, but no alpha
  (momentum loading 0.41, alpha t −1.1). FAIL. The old "pass" really was bias.
- **TRENDVAL → R-2026-11-07-VALMOMSF:** +10.5% vs +7.6%, no alpha, lagged
  2017-24. FAIL.
- **GREENBLATT → R-2026-11-07-MAGICSF:** +14.2% vs +7.6%, every world-class
  gate cleared (alpha t 2.8), held-out 2017-24 lost → FAIL, shortlist 3.
- **Insider clusters (I-2026-10-28-INSIDER): blocked** (2026-11-08). The
  insiders table holds ~50k rows a month and the API does not filter on
  `transactioncode`, so per-ticker queries cannot rebuild it. Needs the bulk
  export (one download) before it can be retested.
- **Retested 2026-11-08:** asset growth (+10.9% vs +8.7%, no alpha), Clenow
  momentum (+11.6%, worst drop −27%), residual momentum (+9.7%, no alpha),
  index deletions (+10.4% but −84% worst drop). All FAIL.

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
13. **A trend overlay destroys quality-value's alpha** (QVTREND, 2026-11-08).
    The trend filter cut the worst drop −57% → −33% but return fell from
    +14.2%/yr to +8.6% and factor alpha from t 2.8 to 0.8: value earns most of
    its premium in the rebounds right after a crash, exactly when the trend
    filter is still out. → Do not trend-gate value; size it instead (or pair
    it with a crisis sleeve held alongside).
14. **Treasury calendar edges stack** (TSYCAL). End-of-month and FOMC windows
    are different days; held together they reach Sharpe 0.92 with a 5% worst
    drop and held up after 2018. They fail t ≥ 3 only because the strategy is
    in the market only about a quarter of trading days. → The rates book is the place for them.
15. **The book keeps improving as uncorrelated pieces are added**: 20 series,
    Sharpe 1.56, 3.2%/yr at 2.0% vol, worst drop −2.9% (11-07: 9 series,
    Sharpe 1.51). The next step is leverage or sizing, not more signals.
16. **Crypto rules mostly fail against buy-and-hold** (6 of 6 tonight). Only
    the BTI trend index improved Sharpe (1.16 vs 0.92, worst drop −54% vs
    −83%) — theme 10 again: crash protection, not extra return.
17. **Two harness bugs found 2026-11-09** (fixed the same night with the owner's go):
    - **crypto is annualised with 252 days, not 365** — every crypto CAGR in
      the ledger is understated (BTC 2015-24 shows 46%/yr; the true figure is
      ~73%). Comparisons against BTC stay fair (both sides scaled alike);
      absolute crypto figures in earlier digests were too low.
    - **mixing Yahoo `=X` FX pairs with ETFs adds FX-only dates** (≥691,
      mostly UK-summer Sundays) on which held ETFs earn nothing — the
      yen/franc sleeves (SAFEHAVEN, HAVENVOL, HAVENRATES) lose some
      Friday→Monday moves. Re-run them once the harness is fixed.
18. **The book is saturating** (2026-11-09). Of nine new series only
    FOMCMOVE raised the book's Sharpe; adding all nine lowers it 1.56 →
    1.51. New blocks must be both uncorrelated AND decent on their own.
    Theme 15 stands: the next gain is sizing/leverage, not more signals.
19. **Value's problem is the mega-cap era, not crashes** (QVBOOK). Holding
    MAGICSF always plus a yen/franc hedge kept the alpha (t 2.87, 14.4%/yr)
    but did not soften 2008 (−56%) and still lost 2017-24. A crisis sleeve
    held alongside is the right shape, but the FX sleeve is too small to
    offset an equity crash; size or a different hedge is the open question.
20. **Investment-style anomalies on honest data are known factors**
    (NETISS, ACCRUALS, FSCORE, LOW-VOL: alpha t 0.1–1.5). Theme 8 confirmed
    for the CMA/RMW family.
21. **Corrections change conclusions — keep auditing the data layer** (2026-11-10).
    The 11-09 harness fix raised every crypto figure (BTC 46%→73%/yr) without
    flipping a verdict, but it LOWERED HAVENVOL (the bug had flattered it), and
    the FX desk found Yahoo `=X` values are start-of-day prices — the two
    FOMC dollar trades measured the wrong day and are withdrawn. With them
    out and HAVENVOL corrected, the book is **Sharpe 1.27** (28 series),
    not 1.56. Every "best block" claim now needs a data-timing check.
    Still open in the harness: `=X` start-of-day dating (rules that read a US
    close and trade `=X` pairs have ~1 day of look-ahead); short legs pay
    instead of earn the T-bill rate in simulate() (blocks market-neutral
    designs, ~1.7–3.4%/yr too low); no financing-spread option.
22. **First harness PASS, broken by the red team** (SLEEVETREND, 2026-11-10).
    10% BTC (trend-gated) inside a 60/40 fund passed every gate (99.8%,
    alpha t 2.75) — but a STATIC 10% BTC sleeve did as well. The edge is
    owning some BTC since 2014, concentrated in 2017; not a rule. →
    Benchmark crypto sleeves against the static sleeve; sizing BTC is an
    owner decision, not a research verdict.
23. **Combining shortlisted blocks works inside an asset class**: CMDBOOK
    (99.4%, held-out win) and RATESLEV (99.3%) are the two strongest results
    to date. Both fail only the multiple-testing gates (DSR, t ≥ 3).
24. **Our first vault test failed** (TSYCALPLUS, 2026-11-11). The Treasury
    calendar overlay passed every harness gate (6.4%/yr vs 3.5%, active t
    4.2) and survived the red team (beats IEF levered to the same average
    exposure by 2.6%/yr; FRED yields confirm the effect). On the sealed
    2024-11 → 2026-11 stretch it returned +3.87% vs IEF +4.02% — the
    pre-registered criterion (beat IEF) failed by 0.15%. Lesson: a real
    historical effect (half of it 2008-11) can still be too small to show
    up in two years net of financing. Family L-TSYCAL's vault is spent.
25. **Commodity book is fragile to a one-sleeve change** (CMDBOOK2): swapping
    in the ag-only skew sleeve dropped 6.9%/yr → 4.5%/yr (93%) and the
    ag-only skew lost money alone. Treat CMDBOOK's 99.4% with caution.
26. **The static BTC sleeve holds on ETFs too** (I-2026-11-07-BTCSLEEVE):
    VT/BND 60/40 + 10% BTC: 11.0%/yr vs 6.3%, Sharpe 0.82 vs 0.47, 99.8%;
    timing rules (trend, vol) add nothing on top. It is a sizing question.
27. **From the options desk, 2026-11-11 (our own journal):** after a side is
    stopped, later same-day entries on that SAME side lost −$9.1k on paper
    (166 sides) and −$5.9k live (89 sides), vs +$10.8k / +$8.2k for all
    others — both halves, both MEIC and MNG, but concentrated in ~5 trend
    days. In-sample; a paper lane would be the honest test (owner decision).
    → Owner "go MEIC 2.0" (2026-11-11): on paper as lane MIIL, beside MIIS
    (1.5x stop), MIIE (11:00 ladder), MIIF ($1.00 shorts), MIIW (50 wings).
28. **Harness fix 2 (2026-11-11) changed no verdict.** Yahoo `=X` values
    were each day's OPENING price (proved on the SNB 2015-01-15 and euro
    2025-04-03 jumps) — now relabelled to the day before; short proceeds
    now earn T-bills (they paid them). 23 affected scripts were re-run as
    corrections (trials.json restored): all still FAIL. Moved up: TOY
    (Russell-vs-S&P year-end spread) 53% → 94%, potential 4; FXVALUE 28% →
    71%; VALMOMFX 17% → 51%; CCYVOLTGT 75% → 82%; HOPTREND 68% → 84%.
    Moved down: the yen/franc crisis sleeves (HAVENVOL 55% → 33%,
    HAVENVOTE 51% → 42%, DOLVOL 55% → 34%) — their edge was partly the
    stale-dating artefact. FOMCUSD / FOMCMOVE stay withdrawn (theme 20).
    Long/short and FX designs are now fairly priced: retest them before
    writing off the classes. `fin_spread=` (annual) charges leverage
    T-bill + spread when a design needs realistic borrowing terms.
29. **League round 1 (2026-11-14): 31 tests, no harness PASS, two
    near-misses that survived their red teams.** CORRMOMREV (commodity
    sectors: momentum when short-term correlation exceeds long-term, else
    reversal; long/short DBA/DBB/DBE/DBP) — 99.86%, fails only t >= 3
    (2.99); the published setting is the best of every grid (honest Sharpe
    ~0.3-0.45), but it is the strongest DIVERSIFIER found so far: corr 0.03
    to the book, +0.14 book Sharpe at 10%. STKBOOK (4 point-in-time stock
    sleeves: R&D, quality-value, net issuance, cash profitability) — fails
    only deflated Sharpe (0.947, 55 trials); a third of its edge over SPY is
    the equal-weight tilt; it LOWERS the book Sharpe (corr 0.63). → Judge
    stock books against an equal-weight/SPY blend; judge long/short
    commodity ideas on book value, not alone.
30. **Yahoo `=X` FX "close" is ~19:00 ET (London midnight), 3 h after the
    US close** (Commodities red team, 2026-11-14). Even after fix 2, a rule
    that reads an FX bar dated i and trades a US-listed asset at close i
    peeks ~3 h ahead: cross-asset rules must read FX bars dated BEFORE the
    trade day. FRED euro-area and UK 3-month rates end 2026-01 (EUR/GBP
    drop out of any carry ranking from ~2026-09 — a vault-run trap).
31. **G10 FX style premia are ~zero 2009-2024 on AQR's own published
    series** (value -0.10/+0.15, momentum -0.10, carry 0.28, multi-style
    0.19 Sharpe): no G10 FX style can clear t >= 3 over our window. FX
    budget belongs to crisis sleeves and diversifiers, and every leg of a
    multi-style must be checked against ITS source series (STYLE3FX's value
    leg was not).
32. **Our own journal (Options team, 2026-11-14):** live MEIC beats its paper
    twin on FILLED sides (+$8.7/side, CI 5-11) — the real-money gap is
    SKIPPED sides (rejections, unfilled reprices: paper twins +$2,214 in the
    confirm half). The GEX split that created MNG did not confirm out of
    sample at the required level (P 0.79); VIX level/change and the vol-risk-
    premium gate did not confirm; holding stopped sides to settlement makes
    more on average but with -$8.6k to -$15.9k days. Data fix owed: 13 live
    rows (09-23/24) carry gross P&L without fees.
33. **Replication gates must match the source's own significance.** Bonds'
    MACROANN was labelled "harness/data suspect" under a t >= 2 gate although
    it reproduced the paper (+10.3bp, t 1.78; source t 1.5-2.5) — it has
    simply reversed since 2002 (-5.2bp). Rule 1 is "sign and rough size".
34. **League round 2 (2026-11-21): 17 tests, one harness PASS, one vault
    test, which failed.** REBALFR (front-running 60/40 rebalancing, long/short
    SPY vs IEF; Harvey-Mazzoleni-Melone 2025) replicated on ETFs (0.78 vs the
    paper's 1.11) and passed every gate (7.4%/yr vs T-bills, t 3.23), but it is
    mostly a next-day SPY-minus-IEF reversal (corr 0.61) that needs market-on-
    close fills, makes 135% of its P&L on 1% of days, and lost money in the
    vault (2024-11..2026-11: -2.7% vs T-bills +8.4%). → A pass driven by
    crisis days needs the vault more than any other; treat stress-day edges
    as sleeves, never as core.
35. **Cost models fitted on live fills must drop sides that never really
    traded** (Crypto red team on Options, 2026-11-21). Nine sides whose live
    stop never executed (cash-settled, the market came back) turned a ~$1/side
    stop cost into "-$62" and a statistically-zero MEIC into "+$17k". Real-
    money MEIC was +$963 over 40 sessions (P 0.57), about -$2.9k without
    that luck. The SIM fill model (paper's pnl_actual) is the one that
    calibrates to live (bias ~$2/side).
36. **MEIC losses come from whipsaw days, and same-side stops cluster on
    trend days.** Both-sides-stopped ("whipsaw") days carry the net loss
    (27 of 52 days, -$12.1k net); one-way days are net positive. A same-side
    lockout (MIIL) saved $2.7k in the -9% week of 11-16..11-20 and matches its
    counterfactual exactly, but the earlier median day saved $0 and the sign
    flips under a 1.5x stop. Prior-day loss / prior-day move did not predict
    bad days (P 0.93 / 0.85, needed 0.95).
37. **Data quality notes (round 2):** Yahoo `=X` has spike-and-revert bad
    prints (19 bars move >=4% and reverse, e.g. EURUSD/USDJPY 2008-12-05
    ~+17%, USDNOK 2020-03-19) and a 2008-07-31..08-26 hole in EUR/JPY/NOK;
    CPER has two bad prints (2014-12-04, 2015-02-02). A spike filter in the
    harness is the owner's call. Sharadar's 8-K events give true earnings-
    release dates from 2004-10; SF3A 13F holder counts start 2013-06.
    Spin-off premium (McConnell-Sibley-Xu) replicates 2006-13 but is gone
    since ~2015 (held-out Sharpe 0.08). AQR's TSMOM-FX did not replicate
    (ours -0.17 vs 0.22; gap in 2010-15 and CHF) even with carry included.
38. **League round 3 (2026-11-28): 10 tests, all FAIL; no vault.** Replication
    worked more often than before (FFDEF on 1934-87 Moody's yields, EAPANN on
    true 8-K dates, FOMCDOL, BTCSEASON) but every replicated premium was
    small, lumpy or faded after ~2010: the earnings-announcement premium is a
    few mega-caps in thin months (+0.13%/month once >=20 names); the FOMC-day
    short-dollar premium is 24.7bp/event 2004-10 but +4.7bp after 2011 with
    five days = 76% of P&L; the default-spread switch is one year (2020).
    CCYCMD hedged against gold earns T-bills (-64% drawdown): its value in
    CMDBOOK is dollar exposure. Cochrane-Piazzesi does not reproduce its tent
    on GSW zeros. Journal QA: the paper journal is sound except the 09-29
    auth-failure rows (FLY was missed by the errata: -$1,433 booked, +$583 at
    settlement) and 11 early-September settlements (net ~$14); QA scripts
    must allow +-$0.51/side for 2-decimal price rounding. CORRMOMREV's vault
    is NOT spent: the vault is only for a harness PASS that survived red team.
39. **Yahoo `=X` dating changes on 2010-08-02** (Commodities red team on FX,
    confirmed by the lead). From 2010-08 the `=X` value is the start-of-day
    price (the harness relabel to the previous bar is right); BEFORE 2010-08
    it is already that day's close, so the relabel puts each value a day
    EARLY - a one-day look-ahead in every =X signal/replication using pre-2010
    data (FX vs CurrencyShares corr 0.60-0.93 at lag -1 before, 0.92 same-day
    after). Affected: haven sleeves (SAFEHAVEN/HAVEN*), FXVALUE, VALMOMFX,
    TSMOM-FX, FOMCUSD/FOMCMOVE, CCYCMD's FX inputs, FOMCDOL's replication.
    **FIXED 2026-11-28 (owner "yes fix research tool"; harness fix 3):**
    `research_bt.FX_START_OF_DAY_FROM = "2010-08-04"` — values before keep
    their date, values from then move to the previous bar; the duplicate at
    the switch is dropped (EUR/GBP/JPY/NZD print the same value 08-03 and
    08-04). Exception: MXN=X switched on 2018-04-04 (same duplicate marker).
    USDCLP=X before 2010 is stale (178 repeated values) — avoid. Verified on
    6 ETF pairs (same-day match in every era after the fix) and FRED noon
    rates (closes back to 1996). 14 affected results re-run as corrections
    (trials restored): no verdict changed; the biggest moves were CCYCMD
    (conf 94.3% -> 91.9%, 5.4% -> 4.9%/yr), CCYDEMAND (67% -> 75%), FXXSMOM,
    PREFOMCDIR, VMEFX (63% -> 54%); FOMCDOL's replication +8.1bp -> +24.7bp
    (t 2.51); FXTSMOM still does not replicate (ours -0.16 vs AQR 0.22).
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
| L-QVTREND | MAGICSF × DD-TREND | **Tested 2026-11-08: FAIL** — cut the drop but killed the alpha (theme 13) |
| L-RATESBOOK | EOMTSY + FOMCUSD + HYTREND(ETF) + SAFEHAVEN | Tonight's book of small uncorrelated rates/FX edges (Sharpe 1.5 at 2.5% vol): size it with risk parity and test it as one sleeve |
| done 2026-11-08 | VALTREND, CORRDUR, GOLDCRISIS, CARRYPROXY, EQCREDIT, MEDIAN, SEASONTREND, TSYCAL | All FAIL; CARRYPROXY, EQCREDIT, MEDIAN, TSYCAL shortlisted at 4 |
| L-QVBOOK | MAGICSF (always on) + yen/franc sleeve | **Tested 2026-11-09: FAIL** — kept the alpha, but the hedge did not soften 2008 and 2017-24 still lagged (theme 19) |
| L-RATESBOOK v2 | TSYCAL + MEDIAN + EQCREDIT + HAVENVOL | **Tested 2026-11-09: FAIL** — Sharpe 0.68 vs 0.32, worst drop −10% vs −24%, 98% confidence; low return because cash sleeves keep their budget. Next: a levered variant |
| done 2026-11-09 | NETISS, ACCRUALS, FSCORE, LOWVOLSF, VIXCORR, SAFEDUR, POLICYMOM, BMP4, UEP, VALMOMFX, HAVENVOTE, DOLVOL, FOMCMOVE, HAVENBASKET, OILCURVETREND, CURVEPAIRS, CMDVALUE, CCYCMD, BTC52WH, MAXMINTREND, BTCQQQGATE, MAJORSXS, BTCTIPP | All FAIL; shortlist adds above |
| done 2026-11-10 | RND, CBOP, LTREV, FOMCCYCLE, QVPARITY; RATESLEV, EMDOLLAR, LOWRISKIG, JANHY, YCMOM; HEDGEUUP, PREFOMCDIR, RRWCMD, OECDCARRY, CMDDXY; GOLDSHOCK, CMDBOOK, NGEIADAY, DEMANDVOTE, CCYCURVE; BOLD, BOLDTREND, BTCSLEEVE10H, SLEEVETREND (red-teamed), BTIFLOOR | All FAIL; CMDBOOK 4, RATESLEV/RND/CCYCURVE 3 |
| done 2026-11-11 | RNDREV, RNDSECT, RNDEAP, INTANGVAL, RDINC; VTCREDIT, FFTERM, BONDCARRYX, CYCLEFAC, TSYCALPLUS (PASS → red team → vault FAIL); GOODCARRY, VIXCARRY, DOLCARRY, LRCARRY, RATEMOM; AGSKEW, CMDBAB, CCYVOLTGT, CMDBOOK2, ETFROLL; BTCSLEEVE (static), BTCVMP, BTCTOM, RPCRYPTO, SLEEVEVOL | All FAIL; every FX carry variant below T-bills even with FRED rates |
| done 2026-11-21 (league round 2) | REBALFR (PASS → red team → vault FAIL), EOMCREDIT, TIPSSEAS; CORRMOMSGL; SPINOFF; QQQBTCBRK, QQQBTCOOS, BTCDVMP; ORGCAP and FXTSMOM not run (replication failed); 9 Options journal studies | All FAIL except LOCKOUTOOS (survives with caveats); FAIRMEIC withdrawn (data error). Queue note: CMDSKEW ag-only and CMDBAB were already run 2026-11-11 |
| done 2026-11-28 (league round 3) | EAPANN, EAPQTR; FFDEF; CURVESPREAD, CCYDEMAND; FOMCDOL; SLEEVEBEST8 (BTCSEASON replicated); Options JOURNALQA, MPMREVIEW, FLYREVIEW (MEIC20GATE not ready until 15 sessions); CPFACTOR not run (replication) | All FAIL; no near-miss. Queue note: CMDTURN and DUALMOMDB already failed in round 1; INTANGMAGIC dropped (INTANGVAL failed) |
| queued by desks (2026-11-11) | FFDEF, MBSVOL (bonds); CMDTURN, DUALMOMDB, CMDASYM (cmd); BTCDVMP, BTCBEST8 (crypto); RNDQUAL, INTANGMAGIC (stocks) | Lower priority if the owner approves the research reset |
| queued by desks (older) | VTCREDIT, FFTERM, BONDCARRYX (bonds); CMDBAB, CCYVOLTGT, CMDSKEW ag-only (cmd); BTCVMP, BTCTOM, I-2026-11-07-BTCSLEEVE static control, RPCRYPTO, QQQBTCBRK (crypto); RNDREV (stocks); DOLCARRY, VIXCARRY, GOODCARRY, HEDGECARRY (FX — FRED now reachable, default Python user-agent; OECD rates lag ~2 months; NFCI is revised — look-ahead) | Next scripts |
| harness fixes (new 2026-11-10) | `=X` start-of-day dating; short-leg T-bill sign in simulate(); financing-spread option | Owner's call — reported in the digest |
| harness fixes | **FIXED 2026-11-09 (owner "fix research tool"):** crypto 365-day annualisation; FX bar dates (+3h); prices carried over gaps. Still open: `rb.sharadar` table param; FX interest | **DONE 2026-11-10:** 21 results re-run as corrections (trials.json restored); every crypto figure up, no verdict changed; HAVENVOL/HAVENVOTE down; RATESBOOK Sharpe 0.68→0.74 |
| data unlocks | insider bulk export; Coin Metrics (on-chain); FRED rates (ETFCARRY / FX carry); EIA inventories; Treasury refunding dates | Blocked ideas waiting on data |

**First portfolio book (2026-11-07):**
- **Contents:** the nine series saved tonight, inverse-vol weighted.
- **Stats:** Sharpe 1.51, 3.8%/yr at 2.5% vol, worst drop −3.6%, 2007-2024 common months.
- **Adds value at 10%:** EOMTSY (+0.10), HYTREND (+0.08), FOMCUSD (+0.04).
- **Dilutes the book:** equity momentum and gross profitability (they add equity beta).
- **Update 2026-11-08:** 20 series, Sharpe 1.56, 3.2%/yr at 2.0% vol, worst
  drop −2.9%. Best adds at 10%: TSYCAL (+0.12), FOMCTSY (+0.07), MEDIAN (+0.03).
- **Update 2026-11-09:** 29 series → Sharpe 1.51, 2.9%/yr at 1.9% vol, worst
  drop −2.7% (the 20-series book stays at 1.56). Only FOMCMOVE adds (+0.05).
- **Correction 2026-11-10:** without the two mis-dated FOMC dollar series and with HAVENVOL corrected, the book is 28 series, **Sharpe 1.27**, 3.2%/yr at 2.5% vol, worst drop −4.4%. Best adds at 10%: RND (+0.09), SLEEVETREND (+0.06, BTC exposure), CBOP (+0.04).
- **Still to do:** rebuild the older shortlist's series (DD-TREND, VTSPYL, HFEA, RPARL…) so they join the book.

Each runs under the vault and automatic trial counting (RESEARCH.md §2b).
