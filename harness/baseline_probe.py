"""Baseline load probe.

Once per minute, measures the round-trip time of a trivial request against
each remote instance (Stellar RPC latest ledger; Rekor log info). Run in
parallel with measurement windows; the output is the per-window baseline
covariate.

Usage: python -m harness.baseline_probe [--minutes 90]
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from typing import Final

import requests
from stellar_sdk import SorobanServer

from .config import REKOR_URL, RPC_URL, RUNS_DIR
from .measure import now_ms

_CSV_PATH: Final = RUNS_DIR / "baseline-probe.csv"
_HEADER: Final[str] = "at_iso;instance;rtt_ms;ok"


def _append(instance: str, rtt_ms: float, ok: bool) -> None:
    if not _CSV_PATH.exists():
        _CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CSV_PATH.write_text(f"{_HEADER}\n", encoding="utf8")
    stamp = datetime.now(timezone.utc).isoformat()
    with _CSV_PATH.open("a", encoding="utf8") as handle:
        handle.write(f"{stamp};{instance};{rtt_ms:.1f};{1 if ok else 0}\n")


def _probe_stellar(server: SorobanServer) -> None:
    t0 = now_ms()
    try:
        server.get_latest_ledger()
        _append("stellar-rpc", now_ms() - t0, True)
    except Exception:  # noqa: BLE001 — probe records failures instead of raising
        _append("stellar-rpc", now_ms() - t0, False)


def _probe_rekor(session: requests.Session) -> None:
    t0 = now_ms()
    try:
        response = session.get(
            f"{REKOR_URL}/api/v1/log", headers={"Accept": "application/json"}, timeout=30
        )
        _append("rekor", now_ms() - t0, response.ok)
    except Exception:  # noqa: BLE001
        _append("rekor", now_ms() - t0, False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline load probe.")
    parser.add_argument("--minutes", type=int, default=90)
    args = parser.parse_args()
    rounds = max(1, args.minutes)
    server = SorobanServer(RPC_URL)
    session = requests.Session()
    print(f"probing every 60 s for {rounds} minutes -> {_CSV_PATH}")
    for i in range(rounds):
        _probe_stellar(server)
        _probe_rekor(session)
        if i < rounds - 1:
            time.sleep(60)


if __name__ == "__main__":
    main()
