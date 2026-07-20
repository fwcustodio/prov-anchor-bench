"""Runs one measurement window: K operations per mechanism, in balanced
randomized order (shuffled blocks of the 4 mechanisms), writing one CSV row
per confirmed operation.

Usage:
    python -m harness.run_pilot --smoke              (K=3, window 0)
    python -m harness.run_pilot --window 1 [--k 13]
"""

from __future__ import annotations

import argparse
import secrets as pysecrets
from datetime import datetime, timezone

from .anchor_classic import ClassicAnchor
from .anchor_control import ControlAnchor
from .anchor_rekor import RekorAnchor
from .anchor_soroban import SorobanAnchor
from .artifacts import build_artifacts
from .config import MECHANISMS, RUNS_DIR, Mechanism, load_secrets
from .measure import OpRecord, append_op_record, median, seeded_shuffle
from .prov import ChainedArtifact, build_chain


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one pilot measurement window.")
    parser.add_argument("--smoke", action="store_true", help="smoke test: K=3, window 0")
    parser.add_argument("--window", type=int, default=None, help="window number (block id)")
    parser.add_argument("--k", type=int, default=None, help="operations per mechanism")
    args = parser.parse_args()
    if args.window is None:
        args.window = 0 if args.smoke else 1
    if args.k is None:
        args.k = 3 if args.smoke else 13
    if args.k <= 0:
        parser.error("--k must be positive")
    return args


def main() -> None:
    args = _parse_args()
    pilot_secrets = load_secrets()
    run_nonce = pysecrets.token_hex(8)
    csv_path = RUNS_DIR / ("smoke-ops.csv" if args.smoke else "pilot-ops.csv")

    artifacts = build_artifacts()
    chain = build_chain(
        [a.as_input() for a in artifacts], "prov-anchor-bench-pilot", run_nonce
    )

    soroban = SorobanAnchor(pilot_secrets.contract_id, pilot_secrets.soroban_secret)
    classic = ClassicAnchor(pilot_secrets.classic_secret)
    rekor = RekorAnchor()
    control = ControlAnchor(f"w{args.window}-{run_nonce}")

    # K blocks, each containing the 4 mechanisms in shuffled order.
    schedule: list[Mechanism] = []
    for block in range(args.k):
        schedule.extend(seeded_shuffle(MECHANISMS, args.window * 1000 + block))

    latencies: dict[Mechanism, list[float]] = {m: [] for m in MECHANISMS}
    op_seq = 0
    for mechanism in schedule:
        link: ChainedArtifact = chain[op_seq % len(chain)]
        op_seq += 1
        submitted_at = datetime.now(timezone.utc).isoformat()
        try:
            if mechanism == "soroban":
                confirmed = soroban.anchor(link)
                record = _row(args.window, op_seq, mechanism, link, submitted_at,
                              confirmed.latency_ms, confirmed.fee_stroops, confirmed.tx_hash, "")
            elif mechanism == "classic":
                confirmed = classic.anchor(link)
                record = _row(args.window, op_seq, mechanism, link, submitted_at,
                              confirmed.latency_ms, confirmed.fee_stroops, confirmed.tx_hash, "")
            elif mechanism == "rekor":
                rekor_result = rekor.anchor(link)
                record = _row(args.window, op_seq, mechanism, link, submitted_at,
                              rekor_result.latency_ms, "", rekor_result.uuid,
                              f"logIndex={rekor_result.log_index}")
            else:
                control_result = control.anchor(link)
                record = _row(args.window, op_seq, mechanism, link, submitted_at,
                              control_result.latency_ms, "", f"offset={control_result.offset}", "")
            latencies[mechanism].append(record.latency_ms)
        except Exception as error:  # noqa: BLE001 — every failure is recorded, not hidden
            record = OpRecord(
                window=args.window, op_seq=op_seq, mechanism=mechanism,
                artifact_id=link.artifact_id, submitted_at_iso=submitted_at,
                latency_ms=-1.0, fee_stroops="", pointer="", status="FAILED",
                note=str(error)[:160],
            )
        append_op_record(csv_path, record)
        latency_text = f"{record.latency_ms:.0f} ms" if record.latency_ms >= 0 else ""
        print(f"[w{args.window} {op_seq:03d}] {mechanism:<7} {record.status} "
              f"{latency_text} {record.pointer[:20]}")

    print(f"\nWindow {args.window} summary (median latency):")
    for mechanism in MECHANISMS:
        values = latencies[mechanism]
        print(f"  {mechanism:<7} n={len(values)}  median={median(values):.0f} ms")
    print(f"\nRows appended to {csv_path}")


def _row(
    window: int,
    op_seq: int,
    mechanism: Mechanism,
    link: ChainedArtifact,
    submitted_at_iso: str,
    latency_ms: float,
    fee_stroops: str,
    pointer: str,
    note: str,
) -> OpRecord:
    return OpRecord(
        window=window, op_seq=op_seq, mechanism=mechanism, artifact_id=link.artifact_id,
        submitted_at_iso=submitted_at_iso, latency_ms=latency_ms, fee_stroops=fee_stroops,
        pointer=pointer, status="SUCCESS", note=note,
    )


if __name__ == "__main__":
    main()
