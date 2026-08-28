---
title: Rates and Wilson
description: >-
  How a boolean outcome becomes a rate with an interval, why Wilson rather than
  the normal approximation, and why no bare proportion can be printed.
---

# Rates and Wilson

Every boolean `outcome` on an item record becomes a rate with a Wilson score interval and
its denominator. There is no code path that produces a bare percentage.
{ .lede }

```console
$ touchstone estimate run-004 --by rung
run-004/estimates.json: 3 estimate(s) from 6772 item(s)
  evidenced [overall]: 3.6% (95% CI 3.2-4.0%, n=6772)
  evidenced [rung=hybas_entry]: 0.0% (95% CI 0.0-0.1%, n=3682)
  evidenced [rung=real_gauge]: 7.8% (95% CI 6.9-8.8%, n=3090)
```

## No bare proportion leaves the laboratory

The formatter takes **counts**, not a rate:

```python
>>> format_rate(36, 84)
'42.9% (95% CI 32.8-53.5%, n=84)'
>>> format_rate(0, 0)
'undefined (n=0)'
```

There is no way to hand it a number that has already lost its denominator. This is a house
rule enforced by a function signature rather than by review.

`n == 0` returns `undefined`, not `0%`. No observations is not the same as a rate of zero.

## Why Wilson

The textbook normal approximation is `p ± z·sqrt(p(1-p)/n)`. It breaks wherever counts
are small or the rate is near zero or one, and **both happen in every stratified
rollup.** It produces intervals that run below 0 or above 1, and it collapses to zero
width at `p = 0`, which is how "0 of 40 failed" becomes "0% (95% CI 0-0%)".

The Wilson score interval is correct in exactly those places. This is the whole of it, as
implemented:

```python title="src/touchstone/stats/proportion.py"
denominator = 1 + z * z / n
centre = (p + z * z / (2 * n)) / denominator
half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
return max(0.0, centre - half), min(1.0, centre + half)
```

The point estimate returned is the plain `k / n`. The interval is centred elsewhere, which
is the correction: Wilson pulls the interval toward 0.5 by an amount that matters when `n`
is small and vanishes when it is not.

Look at the `hybas_entry` row above: 0 successes in 3,682 observations gives `0.0% (95% CI
0.0-0.1%)`. The upper bound is not zero, because 3,682 clean observations do not prove the
rate is zero.

> Wilson, E. B. (1927). Probable inference, the law of succession, and statistical
> inference. *Journal of the American Statistical Association* 22(158), 209-212.

## The denominator is items, not rows

Asking the same item twice does not give two independent observations of the system. When
a plan sets `replicates: 2`, a 60 item pack writes 120 rows, and computing the interval
over 120 would report a precision the run did not buy. The interval narrows with every
replicate added while the rate it is meant to cover stays where it was.

The size of that is worth stating plainly. Over 200 items, a nominal 95% interval computed
across the rows holds:

| Replicates per item | Coverage of a nominal 95% interval |
|---|---|
| 1 | 95% |
| 2 | 91% |
| 5 | 79% |
| 10 | 67% |
| 20 | 54% |

So the interval is computed over **items**. Each item contributes one score, the mean of
its replicates, and the spread across those per-item scores is what the interval is built
from. That spread is carried back into the same Wilson arithmetic through an **effective
sample size**, because rates near zero and one are exactly where Wilson was chosen over
the normal approximation and that reason does not go away here.

The effective size sits between two ends. Replicates that agree perfectly add nothing, so
the floor is the item count: 60 items answered the same way twice are worth 60
observations, not 120. Replicates that are uncorrelated add a full observation each, so
the ceiling is the row count. A run with one replicate has nothing to correct and its
numbers are unchanged, which is why `estimator` still reads `wilson` there and reads
`wilson_clustered` when items repeat.

`k` and `n` stay the raw counts either way, because they are what a reader checks against
the rows. `effective_n` and `design_effect` in `parameters` say what the interval was
actually computed over.

Continuous scores get the same treatment: the bootstrap resamples items rather than rows,
for the same reason and in the same direction.

## What is in the denominator

An item that does not report a metric is **not in that metric's denominator**. It was not
observed, and counting it as a failure would be an invention.

An item that is missing a *stratum key* you asked for lands in a cell called `(unset)`
rather than being dropped, because dropping it would silently shrink the denominator.

## What lands in `estimates.json`

```json
{
  "metric": "evidenced",
  "stratum": {"rung": "real_gauge"},
  "pack_id": "coverage_pack",
  "n": 3090,
  "k": 241,
  "point": 0.078,
  "low": 0.069,
  "high": 0.088,
  "estimator": "wilson",
  "parameters": {"z": 1.96, "confidence": 0.95, "effective_n": 3090.0},
  "reference": "Wilson, E. B. (1927). Probable inference, the law of succession, …"
}
```

Where items were scored more than once, `estimator` reads `wilson_clustered` and
`parameters` also carries `items`, `observations` and `design_effect`.

Every record carries **the method, its parameters and a citation**. An estimate that does
not name its estimator is a number a reviewer has to take on trust. With these fields the
arithmetic can be redone in R, in a spreadsheet, or by hand, without this code.

`pack_id` is kept off `stratum` so that field stays what the pack declared and cannot
collide with a key of the same name.

## 95% and only 95%

`Z_95 = 1.96` is the only interval this tool prints. There is no flag to widen or narrow
it.

An interval whose confidence level moves is an interval whose reader has to check the
level before comparing two numbers, and in practice they do not. The exception is the
[worst-stratum](strata.md) rollup, where a Bonferroni adjustment widens the interval so
that 95% holds *simultaneously* over the cells it selected from. The adjusted `z` is
recorded in `parameters`.

## What the interval is not

**It is sampling error, and only that.** It is how far the number would move if you drew
another set of items the same way.

Three larger errors are not in it:

1. Your items are not a random sample of deployment.
2. Whatever decided `correct` has its own error rate, and that error is correlated with
   the item when the judge is a model.
3. A leaked item set measures recall rather than ability.

It is precision. It is not accuracy. See [What this does not
prove](../project/limits.md).
