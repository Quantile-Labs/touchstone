---
title: Scores and the bootstrap
description: >-
  Continuous measures become means with a BCa bootstrap interval, seeded so the
  number in a bundle is reproducible byte for byte.
---

# Scores and the bootstrap

A continuous `score` on an item record becomes a mean with a bias-corrected and
accelerated bootstrap interval.
{ .lede }

```console
$ touchstone estimate ./run-004 --seed 7 --resamples 2000
```

## Why not a t-interval

A rubric score has no closed-form interval worth using. The percentile bootstrap is biased
whenever the statistic is skewed, and a bounded rubric (0 to 1, or 1 to 5) **always** is:
scores pile up against the ceiling and the sampling distribution of the mean is not
symmetric.

BCa corrects for both the bias and the skew.

> Efron, B. (1987). Better bootstrap confidence intervals. *Journal of the American
> Statistical Association* 82(397), 171-185.
>
> Efron, B., Tibshirani, R. J. (1993). *An Introduction to the Bootstrap*, chapter 14.
> Chapman and Hall.

## How it works

1. Resample the sample with replacement, `resamples` times, computing the statistic each
   time.
2. **Bias correction** `z0`: the normal quantile of the fraction of resamples below the
   observed point estimate. If the bootstrap distribution is centred off the estimate, this
   is by how much.
3. **Acceleration** `a`: from the jackknife. Leave each observation out in turn, and take
   the skewness of the resulting values.
4. Adjust the percentiles the interval is read at by both, then read them off the sorted
   resamples.

Two degenerate cases are handled rather than raised:

- **A sample of one** returns `(point, point, point)`. One observation has no spread.
- **Every resample on one side of the estimate** makes the bias correction undefined. A
  constant sample is the usual cause, and its interval is a point; the full range of the
  resamples is returned.

## Seeded, because an interval nobody can recompute is not evidence

```text
--seed        default 0     the seed for the resampling
--resamples   default 2000  how many resamples
```

Both are recorded in `estimates.json` alongside the interval. The caller passes the seed
the run was frozen with, so the number in the bundle falls out of the plan.

## Why `random()` and not `randrange()`

This is a deliberate implementation choice and it is worth knowing about if you ever port
the arithmetic.

Resampling draws through `random()`:

```python
sample[int(rng.random() * size)]
```

The Python documentation **guarantees** the seeded sequence of `random()` and undertakes to
keep it across versions. `randrange()` reaches its result through `_randbelow`, which is an
implementation detail and has changed before.

An interval that quietly moved on a Python upgrade would be the worst kind of defect here,
because the number it moved is already sealed in somebody's bundle. `tests/test_stats_bootstrap.py`
pins the arithmetic to fixed values, so a change fails the build rather than the client.

`int(random() * size)` is uniform to within the granularity of a 53-bit float, which is
nowhere near the precision any bootstrap interval is quoted to.

## `resamples`

The default is 2000. Efron and Tibshirani, chapter 14: intervals want at least 1000, and
2000 is the usual working figure.

Higher costs only time, and the whole computation is offline. There is no reason to go
lower.

## Stdlib only

No NumPy, no SciPy. The bootstrap is 111 lines of standard library.

That is what lets the package install with the network switched off, and it keeps the
dependency surface of a tool that produces evidence down to three runtime packages. See [Installation](../basics/installation.md#dependencies).
