# RETIRED STRATEGIES — permanent registry

Every strategy retired from the lab is recorded here with its full final
record and the reason. **Before proposing or adopting any new strategy,
check this file** — nothing on this list comes back without new evidence
that the original kill-reason no longer applies. The complete trade-by-
trade history of every retired strategy remains in `data/paper/*.csv`
(nothing is ever deleted) and in the git history of the journal snapshots.

---

## BAND — 10:30 expected-move iron condor
- **Live in lab:** 2026-08-31 → 2026-09-29 (retired by owner instruction)
- **Final record:** 17 condors / 33 sides, **−$2,040**, PF 0.42,
  win rate 18% (per structure), max drawdown −$2,700,
  88% statistical confidence the edge was genuinely negative.
- **Why it died:** the 0.85×straddle band was too tight for September's
  whipsaw sessions — both wings were repeatedly stopped on intraday
  round-trips that closed back inside the band. Containment itself
  measured fine (~70% of closes inside), i.e. the FORECAST was right and
  the trade structure still lost: the per-side "total credit" stop
  converted contained days into double-stop losses.
- **Kept alive:** the 10:30 band SNAPSHOT and the 16:05 containment
  measurement still run every day (`band.trade_enabled: false`) — the
  live bot's settlement accounting and the regime analysis depend on it.
- **Lesson recorded:** tight condors + tight stops in a chop regime lose
  even when the range forecast is correct. Don't re-propose narrow-EM
  condor variants without a chop filter and wider stops.

## LATE — final-hour tight condors (15:00 / 15:30)
- **Live in lab:** 2026-09-17 → 2026-09-29 (retired by owner instruction)
- **Final record:** 16 condors / 32 sides, **−$922**, PF 0.41,
  win rate 19% (per structure), max drawdown −$1,182,
  87% statistical confidence the edge was genuinely negative.
- **Why it died:** the "last hour is the most profitable" premise didn't
  survive contact — 15-wide condors gave the final-hour drift no room,
  so one side was stopped nearly every session while the winning side's
  credit was too small (≈$1/side) to pay for it.
- **Lesson recorded:** last-hour premium exists but cannot be harvested
  with tight symmetric condors; the fly family (whole-structure
  management, wider wings) is the working way to own that window. A
  future last-hour idea must NOT be a narrow condor.

---

*Registry created 2026-09-29. Successors added the same day: MNG (MEIC
mechanics gated to negative-GEX days) and PBW (10:15 put broken-wing
butterfly held to settlement).*
