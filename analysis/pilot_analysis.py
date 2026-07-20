"""Descriptive analysis of pilot runs (stdlib only).

Reads analysis/results/pilot-ops.csv and reports, per mechanism and window:
median/IQR latency, distribution shape (Gamma fit by method of moments),
lag-1..5 autocorrelation of sequential latencies, and a simulation-based
sketch of the repetitions needed to detect mechanism differences.

Usage: python analysis/pilot_analysis.py
"""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"
OPS_CSV = RESULTS_DIR / "pilot-ops.csv"


@dataclass(frozen=True)
class Op:
    window: int
    op_seq: int
    mechanism: str
    latency_ms: float


def load_ops() -> list[Op]:
    ops: list[Op] = []
    with OPS_CSV.open(encoding="utf8") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            if row.get("status") != "SUCCESS":
                continue
            ops.append(
                Op(
                    window=int(row["window"]),
                    op_seq=int(row["op_seq"]),
                    mechanism=row["mechanism"],
                    latency_ms=float(row["latency_ms"]),
                )
            )
    return ops


def quartiles(values: list[float]) -> tuple[float, float, float]:
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[0], statistics.median(values), q[2]


def gamma_moments(values: list[float]) -> tuple[float, float]:
    """Gamma shape/scale by method of moments (exploratory fit)."""
    mean = statistics.fmean(values)
    var = statistics.variance(values) if len(values) > 1 else float("nan")
    if not math.isfinite(var) or var <= 0:
        return float("nan"), float("nan")
    shape = mean * mean / var
    scale = var / mean
    return shape, scale


def acf(values: list[float], max_lag: int = 5) -> list[float]:
    n = len(values)
    if n < max_lag + 2:
        return []
    mean = statistics.fmean(values)
    denominator = sum((v - mean) ** 2 for v in values)
    if denominator == 0:
        return [0.0] * max_lag
    out: list[float] = []
    for lag in range(1, max_lag + 1):
        numerator = sum(
            (values[i] - mean) * (values[i + lag] - mean) for i in range(n - lag)
        )
        out.append(numerator / denominator)
    return out


def lcg_stream(seed: int):
    state = seed & 0xFFFFFFFF
    while True:
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        yield state / 0xFFFFFFFF


def power_sketch(sample_a: list[float], sample_b: list[float], reps_grid: list[int]) -> dict[int, float]:
    """For each candidate n per group, estimates by resampling how often the
    observed median difference between two mechanisms is detected (bootstrap
    CI on the difference excludes zero). Exploratory planning aid only.
    """
    detected: dict[int, float] = {}
    rand = lcg_stream(20260720)
    for n in reps_grid:
        hits = 0
        trials = 400
        for _ in range(trials):
            a = [sample_a[int(next(rand) * len(sample_a))] for _ in range(n)]
            b = [sample_b[int(next(rand) * len(sample_b))] for _ in range(n)]
            diffs = []
            for _ in range(200):
                da = statistics.median(
                    [a[int(next(rand) * n)] for _ in range(n)]
                )
                db = statistics.median(
                    [b[int(next(rand) * n)] for _ in range(n)]
                )
                diffs.append(da - db)
            diffs.sort()
            low = diffs[int(0.025 * len(diffs))]
            high = diffs[int(0.975 * len(diffs)) - 1]
            if low > 0 or high < 0:
                hits += 1
        detected[n] = hits / trials
    return detected


def main() -> None:
    ops = load_ops()
    if not ops:
        print(f"no SUCCESS rows found in {OPS_CSV}")
        return
    mechanisms = sorted({op.mechanism for op in ops})
    windows = sorted({op.window for op in ops})
    print(f"{len(ops)} successful operations, windows={windows}\n")

    print("== Latency by mechanism (all windows pooled) ==")
    by_mechanism: dict[str, list[float]] = {m: [] for m in mechanisms}
    for op in ops:
        by_mechanism[op.mechanism].append(op.latency_ms)
    for mechanism in mechanisms:
        values = by_mechanism[mechanism]
        q1, med, q3 = quartiles(values)
        shape, scale = gamma_moments(values)
        print(
            f"  {mechanism:<8} n={len(values):<4} median={med:8.1f} ms  "
            f"IQR=[{q1:.1f}, {q3:.1f}]  gamma(shape={shape:.2f}, scale={scale:.1f})"
        )

    print("\n== Median latency per window ==")
    for window in windows:
        parts: list[str] = []
        for mechanism in mechanisms:
            values = [
                op.latency_ms for op in ops if op.window == window and op.mechanism == mechanism
            ]
            if values:
                parts.append(f"{mechanism}={statistics.median(values):.0f}")
        print(f"  w{window}: " + "  ".join(parts))

    print("\n== Lag-1..5 autocorrelation of sequential latencies (per window, remote mechanisms) ==")
    for window in windows:
        for mechanism in mechanisms:
            if mechanism == "control":
                continue
            series = [
                op.latency_ms
                for op in sorted(ops, key=lambda o: o.op_seq)
                if op.window == window and op.mechanism == mechanism
            ]
            coefficients = acf(series)
            if coefficients:
                text = " ".join(f"{c:+.2f}" for c in coefficients)
                print(f"  w{window} {mechanism:<8} {text}")

    soroban = by_mechanism.get("soroban", [])
    classic = by_mechanism.get("classic", [])
    if len(soroban) >= 5 and len(classic) >= 5:
        print("\n== Power sketch: detecting soroban vs classic median difference ==")
        for n, rate in power_sketch(soroban, classic, [5, 10, 20, 30]).items():
            print(f"  n={n:<3} per mechanism -> detection rate ~{rate:.2f}")

    print("\nExploratory description only — no hypothesis tests (see docs/protocolo-piloto.md).")


if __name__ == "__main__":
    main()
