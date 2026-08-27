---
title: Score card anatomy
description: >-
  The rubric as data: an ordered ladder, thresholds, ceilings and indicators, all read
  from YAML by an engine that has no rubric of its own.
---

# Score card anatomy

A score card is the rubric, as data. The ladder, the thresholds and the ceilings are all
read from the file.
{ .lede }

```console
$ touchstone grade ./run-004 --score-card examples/scorecard.yaml
```

!!! danger "`examples/scorecard.yaml` is not a standard"

    The levels, the thresholds and the ceilings in it are invented to show the shape of the
    file and to make the command runnable. **Do not cite them and do not copy the numbers
    into anything real.** What counts as fit for service is a policy judgment about
    acceptable harm in a named use case, and a number invented in an example becomes
    precedent the first time somebody quotes it.

## The engine has no rubric

`levels` is an ordered list the card declares, best first, and nothing in the engine knows
how many there are or what they are called.

An engine that hardcodes A-to-E cannot carry a standard that has not been finished yet, and
several are not finished yet. A card with three levels and a card with eight both work.

```yaml
score_card_name: "example"
levels: ["A", "B", "C", "unfit"]
```

## Top-level fields

| Field | Type | Notes |
|---|---|---|
| `score_card_name` | string | Required. |
| `levels` | list, ≥ 2 | **Ordered best first.** Every level named anywhere in the card must appear here. |
| `tier_ceilings` | map | Access tier → best level it may reach. See [Tier ceilings](ceilings.md). |
| `summary_only_ceiling` | string | Best level a metric from a pack that emitted no items may reach. |
| `indicators` | list, ≥ 1 | Required. |

The card is validated as a whole before anything is graded: duplicate levels, duplicate
indicator ids, and any level named by a rule or a ceiling that is not in `levels` are all
errors.

## An indicator

```yaml
indicators:
  - id: headline_accuracy
    name: "Correct answers over the whole sample"
    metric:
      source: estimate
      name: correct
      pack_id: example_pack
    assessment:
      - level: "A"
        condition: greater_equal_ci_lower
        threshold: 0.9
        description: "the lower bound clears 0.9"
      - level: "B"
        condition: greater_equal_ci_lower
        threshold: 0.7
      - level: "C"
        condition: greater_equal_ci_lower
        threshold: 0.5
      - level: "unfit"
        condition: greater_equal
        threshold: 0.0
```

| Field | Notes |
|---|---|
| `id` | Required. `^[a-z0-9_]{1,32}$`, unique in the card. |
| `name` | Optional, human-readable. |
| `metric` | A [metric reference](#metric-references), an [expression](expressions.md), or an [audit reference](audit.md). |
| `assessment` | Ordered, **best level first**. The first rule that holds decides. |
| `tier_ceilings` | Optional per-indicator override. See [Tier ceilings](ceilings.md). |

`assessment` may be empty **only** for an audit indicator, where the ladder is the
assessor's. A computed indicator with no rules has nothing to grade with, and a rule with
no threshold would be a rule that always holds, which is a typo. Both are refused.

## Metric references

Which number in `estimates.json` the indicator is about.

```yaml
metric:
  source: estimate
  name: correct
  pack_id: example_pack
  stratum: {}
```

| Field | Default | Notes |
|---|---|---|
| `source` | `estimate` | One of `estimate`, `worst_stratum`, `calibration`, `replicate_variance`. |
| `name` | none | Required. The metric key, as the pack reported it. |
| `pack_id` | `null` | `null` selects the **pooled** figure. |
| `stratum` | `{}` | Empty is the whole sample. Ignored by `worst_stratum`. |
| `bundle` | `this` | `prior` reads the previous evaluation. See [Comparing to a prior bundle](prior.md). |
| `keys` | `[]` | `worst_stratum` only. |
| `min_n` | `30` | `worst_stratum` only. |
| `higher_is_better` | `true` | `worst_stratum` only. |

!!! warning "`pack_id: null` on a multi-pack run is rarely what you meant"

    It grades the pooled figure, with two packs both reporting `correct` counted into one
    denominator. They are not measuring the same thing. `grade` says so rather than
    grading them as though they were.

### Which sources carry an interval

| Source | Interval |
|---|---|
| `estimate` | **yes**, Wilson or BCa |
| `worst_stratum` | **yes**, Bonferroni-widened |
| `calibration` | no |
| `replicate_variance` | no |

An ECE and a replicate spread are single numbers; neither has a sampling distribution this
codebase is willing to assert. Asking for an interval condition on one is a **plan error**,
raised, rather than a false answer. See [Conditions](conditions.md).

## The four `metric.source` values

```yaml title="a rate over the whole sample"
metric: {source: estimate, name: correct, pack_id: example_pack}
```

```yaml title="the weakest cell of at least thirty items"
metric:
  source: worst_stratum
  name: correct
  pack_id: example_pack
  keys: ["language"]
  min_n: 30
  higher_is_better: true
```

```yaml title="expected calibration error"
metric: {source: calibration, name: correct, pack_id: example_pack}
```

```yaml title="how far the rate moved between replicates"
metric: {source: replicate_variance, name: correct, pack_id: example_pack}
```

## What comes out

`scorecard.json`, in the bundle:

```json
{
  "touchstone_version": "0.1.0",
  "score_card_name": "example",
  "access_tier": "black_box",
  "levels": ["A", "B", "C", "unfit"],
  "plan_sha256": "81c63db1…",
  "indicators": [
    {
      "id": "headline_accuracy",
      "verdict": "graded",
      "level": "B",
      "uncapped_level": "A",
      "ceiling": "B",
      "ceiling_reason": "access_tier",
      "rule": {"level": "A", "condition": "greater_equal_ci_lower", "threshold": 0.9},
      "value": 0.94,
      "measured": [{"ref": {…}, "value": 0.94, "low": 0.924, "high": 0.954, "n": 1000}]
    }
  ]
}
```

Three things there are the point of the format:

- **`access_tier` is copied from the frozen plan, not from a flag**, so the ceiling that
  applied is part of the evidence.
- **`levels` is carried in the output**, so the bundle is readable without the score card
  that produced it.
- **`plan_sha256`** names the frozen plan these grades were asserted against. A grade is
  only meaningful beside thresholds that were fixed before the run.

`uncapped_level` is what the ladder awarded before any ceiling applied, kept so a reader can
see both the claim the evidence supported and the reason it was not made.

## Verdicts

| Verdict | Meaning |
|---|---|
| `graded` | a level was awarded |
| `indeterminate` | the interval straddles a boundary. See [Indeterminate](indeterminate.md) |
| `ungraded` | no rule held at all, or there was nothing to grade |

**`ungraded` sits outside the ladder.** It says the ladder had nothing to say, or that the
number was never in the bundle. A reader who takes it for the worst level has read it
wrong.
