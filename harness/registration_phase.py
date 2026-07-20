"""Times the artifact-registration phase with and without anchoring.

This is the numerator/denominator of the end-to-end overhead question: the
registration phase covers building the provenance records for all pipeline
artifacts and (in the "with" condition) anchoring every artifact through one
mechanism.

Usage:
    python -m harness.registration_phase --without --reps 3
    python -m harness.registration_phase --with-mechanism control --reps 3
    python -m harness.registration_phase --with-mechanism soroban --reps 1
"""

from __future__ import annotations

import argparse
import secrets as pysecrets
from datetime import datetime, timezone
from typing import Final

from .anchor_classic import ClassicAnchor
from .anchor_control import ControlAnchor
from .anchor_rekor import RekorAnchor
from .anchor_soroban import SorobanAnchor
from .artifacts import build_artifacts
from .config import RUNS_DIR, Mechanism, load_secrets
from .measure import now_ms
from .prov import build_chain

_CSV_PATH: Final = RUNS_DIR / "registration-phase.csv"
_HEADER: Final[str] = "at_iso;condition;mechanism;artifacts;duration_ms"


def _append(condition: str, mechanism: str, artifacts: int, duration_ms: float) -> None:
    if not _CSV_PATH.exists():
        _CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CSV_PATH.write_text(f"{_HEADER}\n", encoding="utf8")
    stamp = datetime.now(timezone.utc).isoformat()
    with _CSV_PATH.open("a", encoding="utf8") as handle:
        handle.write(f"{stamp};{condition};{mechanism};{artifacts};{duration_ms:.1f}\n")


def _run_without() -> None:
    t0 = now_ms()
    artifacts = build_artifacts()
    build_chain([a.as_input() for a in artifacts], "prov-anchor-bench-pilot", pysecrets.token_hex(8))
    duration = now_ms() - t0
    _append("without", "-", len(artifacts), duration)
    print(f"without anchoring: {duration:.0f} ms ({len(artifacts)} artifacts)")


def _run_with(mechanism: Mechanism) -> None:
    pilot_secrets = load_secrets()
    run_nonce = pysecrets.token_hex(8)
    t0 = now_ms()
    artifacts = build_artifacts()
    chain = build_chain([a.as_input() for a in artifacts], "prov-anchor-bench-pilot", run_nonce)
    if mechanism == "soroban":
        soroban = SorobanAnchor(pilot_secrets.contract_id, pilot_secrets.soroban_secret)
        for link in chain:
            soroban.anchor(link)
    elif mechanism == "classic":
        classic = ClassicAnchor(pilot_secrets.classic_secret)
        for link in chain:
            classic.anchor(link)
    elif mechanism == "rekor":
        rekor = RekorAnchor()
        for link in chain:
            rekor.anchor(link)
    else:
        control = ControlAnchor(f"reg-{run_nonce}")
        for link in chain:
            control.anchor(link)
    duration = now_ms() - t0
    _append("with", mechanism, len(chain), duration)
    print(f"with anchoring via {mechanism}: {duration:.0f} ms ({len(chain)} artifacts)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Registration-phase timing.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--without", action="store_true", help="pipeline without anchoring")
    group.add_argument(
        "--with-mechanism",
        choices=["soroban", "classic", "rekor", "control"],
        help="pipeline with anchoring through one mechanism",
    )
    parser.add_argument("--reps", type=int, default=3)
    args = parser.parse_args()
    for _ in range(max(1, args.reps)):
        if args.without:
            _run_without()
        else:
            mechanism: Mechanism = args.with_mechanism
            _run_with(mechanism)
    print(f"rows appended to {_CSV_PATH}")


if __name__ == "__main__":
    main()
