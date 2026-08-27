---
title: Strata and rollup
description: >-
  Grouping items into cells with --by, and the worst-stratum rule that finds the
  weakest cell without letting selection inflate it.
---

# Strata and rollup

`--by` splits a metric by any dimension the pack tagged its items with.
{ .lede }

```console
$ touchstone estimate run-004 --by rung
run-004/estimates.json: 3 estimate(s) from 6772 item(s)
  evidenced [overall]: 3.6% (95% CI 3.2-4.0%, n=6772)
  evidenced [rung=hybas_entry]: 0.0% (95% CI 0.0-0.1%, n=3682)
  evidenced [rung=real_gauge]: 7.8% (95% CI 6.9-8.8%, n=3090)
```

## The engine never names a key

The strata are open dimensions, declared by the pack rather than by this engine. The rollup
takes the keys it is asked for and reports the cells it finds.

This is why a pack for any market works without a change to the engine: `language`,
`rung`, `applicant_band`, `clinic_type` are all the same to it.

## Repeat `--by` for each key on its own *and* crossed

```console
$ touchstone estimate run-004 --by language --by difficulty
```

That produces, for each metric:

- the overall cell
- each `language` cell
- each `difficulty` cell
- each `language × difficulty` cell

Crossing multiplies cells fast, and cells get thin fast. Every cell carries its own `n`,
which is the point: **a cell without its denominator is how a three-item result becomes a
headline.**

## Missing keys become `(unset)`

An item missing a requested stratum key lands in a cell called `(unset)` rather than being
dropped. Dropping it would silently shrink the denominator, and a denominator that moves
for reasons the reader cannot see is worse than an ugly cell name.

## Worst stratum

The headline number hides the cell that matters. A system at 91% overall can be at 43% in
one language, and the 91% is the number that ends up in the summary.

A `worst_stratum` metric finds that cell:

```yaml title="examples/scorecard.yaml"
metric:
  source: worst_stratum
  name: correct
  pack_id: example_pack
  keys: ["language"]
  min_n: 30
  higher_is_better: true
```

### `min_n`, and the cells it kept out

Cells below `min_n` are **reported, not dropped**:

```json
{
  "metric": "correct",
  "min_n": 30,
  "higher_is_better": true,
  "worst": { "stratum": {"language": "ha"}, "n": 71, "point": 0.62, "low": 0.51, "high": 0.72, … },
  "excluded": [
    { "stratum": {"language": "ig"}, "n": 12, … }
  ],
  "selected_from": 4
}
```

A rollup that quietly discards its thin cells reads as coverage it does not have. If
`language=ig` had 12 items, that is a fact about the evaluation, and it belongs where the
reader will see it.

`worst: null` when no cell reaches `min_n`. **Read that as a finding:** the evaluation was
not stratified deeply enough to support a claim about any subgroup.

### Selection inflates the extreme, so the interval widens

Picking the minimum of several noisy estimates biases it downward. The more cells you pick
from, the more extreme the winner, even when every cell has the same true rate.

So the interval on `worst` is widened by a **Bonferroni adjustment** to hold
simultaneously over all the eligible cells:

```python
bonferroni_z(comparisons, confidence=0.95)
# comparisons == 1 and confidence == 0.95 returns exactly Z_95 = 1.96
```

One comparison returns `1.96` rather than the exact `1.959964`, so a rollup with a single
eligible cell prints the same arithmetic as everywhere else in the tool and a reader is not
asked to account for a difference in the sixth decimal that means nothing.

> Miller, R. G. (1981). *Simultaneous Statistical Inference*, 2nd edition. Springer,
> chapter 1.

`selected_from` records how many eligible cells the winner was ranked against. It is the
number that makes the widened interval readable, and **a reader who sees it rise knows the
point estimate is being selected harder.**

### `higher_is_better`

Which end is "worst". `true` for an accuracy rate, `false` for an error rate or a latency.

## Declaring strata

```yaml title="manifest.yaml"
strata:
  - name: "language"
    values: ["en", "pcm", "ha", "yo", "ig"]
```

Declared so a plan and a score card can be checked before anything runs. The values are
yours; Touchstone never interprets them.
