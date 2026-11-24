"""Paired randomization test and bootstrap confidence intervals between two runs. [W1-B2]

Inputs are per-query metric values for the same queries, in the same order."""
import random


def paired_randomization(a, b, n=10000, seed=0) -> float:
    """Two-sided p-value: randomly swap each query's pair and count mean differences as large as observed."""
    d = [x - y for x, y in zip(a, b)]
    obs = abs(sum(d))
    rng = random.Random(seed)
    hits = sum(abs(sum(x if rng.random() < 0.5 else -x for x in d)) >= obs - 1e-12 for _ in range(n))
    return (hits + 1) / (n + 1)


def bootstrap_ci(values, n=10000, alpha=0.05, seed=0) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean over queries."""
    rng = random.Random(seed)
    m = len(values)
    means = sorted(sum(rng.choices(values, k=m)) / m for _ in range(n))
    return means[int(n * alpha / 2)], means[int(n * (1 - alpha / 2)) - 1]
