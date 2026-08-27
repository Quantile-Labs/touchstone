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
p = k / n
denominator = 1 + z * z / n
centre = (p + z * z / (2 * n)) / denominator
half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
return p, max(0.0, centre - half), min(1.0, centre + half)
```

The point estimate returned is the plain `k / n`. The interval is centred elsewhere, which
is the correction: Wilson pulls the interval toward 0.5 by an amount that matters when `n`
is small and vanishes when it is not.

Look at the `hybas_entry` row above: 0 successes in 3,682 observations gives `0.0% (95% CI
0.0-0.1%)`. The upper bound is not zero, because 3,682 clean observations do not prove the
rate is zero.

> Wilson, E. B. (1927). Probable inference, the law of succession, and statistical
> inference. *Journal of the American Statistical Association* 22(158), 209-212.

## The denominator

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
  "parameters": {"z": 1.96, "confidence": 0.95},
  "reference": "Wilson, E. B. (1927). Probable inference, the law of succession, …"
}
```

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
