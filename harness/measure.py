"""Measurement primitives: op records, CSV output, monotonic clock, seeded shuffle."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Sequence, TypeVar

_HEADER: Final[str] = (
    "window;op_seq;mechanism;artifact_id;submitted_at_iso;latency_ms;"
    "fee_stroops;pointer;status;note"
)

T = TypeVar("T")


@dataclass(frozen=True)
class OpRecord:
    """One measured anchoring operation."""

    window: int
    op_seq: int
    mechanism: str
    artifact_id: str
    submitted_at_iso: str
    latency_ms: float
    fee_stroops: str
    pointer: str
    status: Literal["SUCCESS", "FAILED"]
    note: str


def append_op_record(csv_path: Path, record: OpRecord) -> None:
    if not csv_path.exists():
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(f"{_HEADER}\n", encoding="utf8")
    line = ";".join(
        [
            str(record.window),
            str(record.op_seq),
            record.mechanism,
            record.artifact_id,
            record.submitted_at_iso,
            f"{record.latency_ms:.1f}",
            record.fee_stroops,
            record.pointer,
            record.status,
            record.note.replace(";", ","),
        ]
    )
    with csv_path.open("a", encoding="utf8") as handle:
        handle.write(f"{line}\n")


def now_ms() -> float:
    """Milliseconds from the monotonic clock."""
    return time.perf_counter() * 1000.0


def seeded_shuffle(items: Sequence[T], seed: int) -> list[T]:
    """Fisher-Yates with a deterministic LCG so runs are reproducible per seed."""
    result = list(items)
    state = seed & 0xFFFFFFFF

    def next_unit() -> float:
        nonlocal state
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        return state / 0xFFFFFFFF

    for i in range(len(result) - 1, 0, -1):
        j = int(next_unit() * (i + 1))
        result[i], result[j] = result[j], result[i]
    return result


def median(values: Sequence[float]) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0
