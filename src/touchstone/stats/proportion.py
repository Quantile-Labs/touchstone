"""Proportions, with the interval attached.

The house rule is that no bare proportion leaves the laboratory, so the formatter here
takes the counts rather than a rate: there is no way to hand it a number that has already
lost its denominator.
"""

from math import nan, sqrt

Z_95 = 1.96
"""Two-sided normal quantile for 95 percent. The only interval this tool prints."""

WILSON_REFERENCE = (
    "Wilson, E. B. (1927). Probable inference, the law of succession, and statistical "
    "inference. Journal of the American Statistical Association 22(158), 209-212."
)


def wilson(k: int, n: int, z: float = Z_95) -> tuple[float, float, float]:
    """Wilson score interval for a proportion. Returns (point, low, high).

    Correct where the normal approximation breaks, which is wherever counts are small or
    the rate is near zero or one, and both happen in every stratified rollup. n == 0
    gives (nan, 0.0, 1.0): no observations is not the same as a rate of zero.
    """
    if n < 0 or k < 0:
        raise ValueError(f"counts cannot be negative: k={k}, n={n}")
    if k > n:
        raise ValueError(f"more successes than observations: k={k}, n={n}")
    if n == 0:
        return nan, 0.0, 1.0

    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return p, max(0.0, centre - half), min(1.0, centre + half)


def format_rate(k: int, n: int, dp: int = 1) -> str:
    """Render a proportion the way it has to appear: point, interval, denominator.

    Takes counts, not a rate, so a bare proportion cannot be formatted at all.

    >>> format_rate(36, 84)
    '42.9% (95% CI 32.8-53.5%, n=84)'
    >>> format_rate(0, 0)
    'undefined (n=0)'
    """
    if n == 0:
        return "undefined (n=0)"
    point, low, high = wilson(k, n)
    return f"{point * 100:.{dp}f}% (95% CI {low * 100:.{dp}f}-{high * 100:.{dp}f}%, n={n})"
