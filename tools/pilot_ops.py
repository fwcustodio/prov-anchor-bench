"""Reader for the per-operation pilot CSV (analysis/results/pilot-ops.csv)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from harness.config import MECHANISMS, Mechanism

DEFAULT_OPS_CSV: Final[Path] = Path(__file__).resolve().parent.parent / "analysis" / "results" / "pilot-ops.csv"


@dataclass(frozen=True)
class PilotOp:
    window: int
    op_seq: int
    mechanism: Mechanism
    artifact_id: str
    submitted_at: datetime
    latency_ms: float
    fee_stroops: str
    pointer: str
    status: str
    note: str


def _mechanism(raw: str) -> Mechanism:
    for mechanism in MECHANISMS:
        if mechanism == raw:
            return mechanism
    raise ValueError(f"unknown mechanism '{raw}'")


def load_pilot_ops(path: Path = DEFAULT_OPS_CSV) -> list[PilotOp]:
    ops: list[PilotOp] = []
    with path.open(encoding="utf8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            ops.append(
                PilotOp(
                    window=int(row["window"]),
                    op_seq=int(row["op_seq"]),
                    mechanism=_mechanism(row["mechanism"]),
                    artifact_id=row["artifact_id"],
                    submitted_at=datetime.fromisoformat(row["submitted_at_iso"]),
                    latency_ms=float(row["latency_ms"]),
                    fee_stroops=row["fee_stroops"],
                    pointer=row["pointer"],
                    status=row["status"],
                    note=row["note"],
                )
            )
    return ops
