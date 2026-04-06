# Tactical Evaluation Model Validation Pass (2026-04-06)

## Scope
Validation pass against current app data/model outputs for:
- Tactics Breakdown
- Recent Tactics Breakdown
- Testing Tactics
- Tactical Set Recommendation

Method used:
- Executed the same transformation/status functions used by UI pages.
- Reviewed strong, weak, and low-sample tactics.
- Checked evidence-tier labeling and recommendation coverage behavior.

## Data Snapshot
- Total tactic rows in breakdown model: 124
- Recent (last 7 days) tactic rows: 47
- Testing-tactics rows (<= 25 rounds, last 7 days): 32
- Tactical set recommendation contexts evaluated by largest samples:
  - Train/Red (1409 rounds)
  - Train/Blue (1318 rounds)
  - Castle/Red (908 rounds)
  - Castle/Blue (870 rounds)

## Validation Goals

### 1) Quality, confidence, context, coverage, and set-inclusion are visibly affecting outcomes
**Pass (mostly).**
- Status distribution is broad (`Situational`, `Drop`, `Risky`, `Strong Keep`, `Test More`, `Keep`, `Refine`) rather than purely win-rate sorted.
- High weighted deltas can still be held back by low sample/context (`Test More` on 1–3 round rows), showing confidence gates are active.
- Stomp/context logic is active: high raw WR tactics are being tagged `Refine`/`Risky` when stomp inflation is high.
- Recommendation layer shows explicit bucket-coverage forcing (Pistol/Eco/Standard lanes) and can include fallback picks to cover missing core buckets.

### 2) Easy stomp-match tactics are being downweighted vs competitive/deeper evidence
**Pass with one caveat.**
- Example downweight behavior appears correctly:
  - `Train Red (S)A - Fast Flash`: raw WR 95.8%, weighted WR 86.9%, stomp inflation 17.2, status `Refine` with stomp-focused explanation.
  - `Train Blue (P)A - AntiRush > PopDog Hold`: raw WR 82.5%, weighted WR 74.7%, stomp inflation 15.0, status `Refine`.
- Caveat: some very high weighted-delta rows with tiny samples still appear visually “elite” numerically before status is read (e.g., 1-round rows).

### 3) S-tier evidence materially improves tactic evaluation
**Pass.**
- Weighted model reacts meaningfully to tier mix.
- Multiple rows show weighted WR changing versus raw WR based on higher-tier outcomes.
- Rows with strong S/A/B exposure (`high_tier_round_share` ~0.99–1.00) and positive S-tier deltas move into `Strong Keep`/`Keep`/`Promising` cohorts when sample is sufficient.

### 4) B-tier-only samples are no longer described as if they have S/A/B evidence
**Mostly pass, but not perfect.**
- Explicitly improved behavior exists:
  - `Positive B-tier evidence...`
  - `Promising B-tier return, but no S/A sample yet.`
- Remaining issue found:
  - A small number of B-only rows still get generic phrasing that can feel too broad (e.g., “deeper tactical matches” wording) even when only B-tier exists.
  - In this pass, 2 B-only rows were flagged by keyword scan for potentially overreaching tier language.

### 5) Smaller tactic-box descriptions feel more informative/evidence-based
**Pass.**
- Reason text now references model features directly (weighted edge, S-tier deltas, stomp inflation, sample depth, recency, context confidence).
- Descriptions are generally specific to failure/success mode rather than generic “good/bad tactic” labels.

### 6) Tactical Set Recommendation feels smarter/coverage-aware, not just reshuffled
**Pass, with one practical caveat.**
- Coverage logic is clearly active:
  - Core bucket targeting pulls Pistol/Eco/Standard lanes.
  - Optional/split coverage logic changes order/selection.
- Caveat:
  - In thin contexts, fallback coverage can force in weak/excluded tactics (e.g., Backup / Exclude-For-Now rows) to satisfy core coverage. This is logically consistent with coverage-first design but can look counterintuitive if users expect pure quality ranking.

## What Is Clearly Improved
- Stomp inflation suppression is meaningfully visible in statuses/reasons.
- Higher-tier weighting is visibly shaping scores and statuses.
- Evidence-aware language in cards is materially better than generic commentary.
- Low-sample tactics are mostly prevented from being over-locked, even with flashy early WR.
- Recommendation set now behaves like a constrained lineup builder (coverage + quality), not a simple top-7 sort.

## What Still Feels Off
1. **Some strong-looking tactics are arguably too cautious**
   - Several tactics with very high weighted deltas remain `Test More`/`Situational` due to tiny sample sizes; this is defensible statistically, but can feel conservative in UI.
2. **B-only language still occasionally over-broad**
   - A few B-only cases still receive text that sounds more comprehensive than the underlying evidence.
3. **Coverage fallback can surface weak picks**
   - Recommendation sets can include `Backup`/`Exclude For Now` entries in order to satisfy required core coverage, which may feel like quality regressions to users.
4. **Perception gap on high positive rows**
   - When a row shows large positive weighted delta but status is non-committal, users may interpret as inconsistency unless confidence/sample cues are more prominent.

## High-Leverage Small Follow-Ups
1. **Tighten B-only phrasing guardrails in all generic branches**
   - Ensure every B-only path avoids “higher-tier” sounding language unless S/A exists.
2. **Add a visible “sample confidence band” badge directly on cards**
   - Example: `Tiny sample`, `Developing sample`, `Stable sample` to reduce strong-but-cautious confusion.
3. **Recommendation fallback policy tweak (small)**
   - Keep coverage guarantees, but add a stronger penalty for `Backup`/`Exclude For Now` when alternatives exist, even if coverage becomes partially incomplete.
4. **Surface stomp/context penalties in compact form**
   - Add one short line like `Context: competitive` vs `Context: stomp-heavy` to explain why high WR may be downgraded.

## Bottom Line
The multi-component model is behaving materially better in practical outputs: it is more evidence-sensitive, more tier-aware, and more coverage-aware than before. Main remaining polish is around edge-case wording (especially B-only), tiny-sample perception management, and balancing coverage constraints against weak fallback picks.
