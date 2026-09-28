"""Archives the public evidence behind every remote pilot operation.

For each Stellar row (soroban, classic) it stores the Horizon transaction and
its operations; for each Rekor row, the log entry; and the deployed contract
bytecode. Stored under evidence/<label>/ so the published results stay
verifiable after a testnet reset. Existing files are kept (idempotent).

Usage: python -m tools.archive_evidence [--label pilot-v1] [--ops PATH] [--contract C...]
"""

from __future__ import annotations

import argparse
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import requests
from stellar_sdk import SorobanServer

from harness.config import REKOR_URL, REPO_ROOT, RPC_URL

from .jsontypes import JsonObject, JsonValue, parse_json, write_json
from .pilot_ops import DEFAULT_OPS_CSV, PilotOp, load_pilot_ops

HORIZON_URL: Final[str] = "https://horizon-testnet.stellar.org"
PILOT_V1_CONTRACT: Final[str] = "CB6CW2PRULKUBZWJPONROCSV7L6TXQEIVR4N2SZURQX56XHYA5I6LCGM"


def get_json(session: requests.Session, url: str) -> JsonValue:
    for attempt in range(4):
        response = session.get(url, headers={"Accept": "application/json"}, timeout=30)
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(2.0 * (attempt + 1))
            continue
        response.raise_for_status()
        # Rekor omits the charset; decode explicitly so checkpoint notes stay intact.
        return parse_json(response.content.decode("utf8"))
    raise RuntimeError(f"giving up after retries: {url}")


def _archive_stellar(session: requests.Session, op: PilotOp, target: Path) -> str:
    if target.exists():
        return "kept"
    transaction = get_json(session, f"{HORIZON_URL}/transactions/{op.pointer}")
    operations = get_json(session, f"{HORIZON_URL}/transactions/{op.pointer}/operations?limit=20")
    document: JsonObject = {"transaction": transaction, "operations": operations}
    write_json(target, document)
    return "saved"


def _archive_rekor(session: requests.Session, op: PilotOp, target: Path) -> str:
    if target.exists():
        return "kept"
    write_json(target, get_json(session, f"{REKOR_URL}/api/v1/log/entries/{op.pointer}"))
    return "saved"


def _archive_one(session: requests.Session, op: PilotOp, out_dir: Path) -> str:
    if op.status != "SUCCESS":
        return "skipped"
    if op.mechanism in ("soroban", "classic"):
        return _archive_stellar(session, op, out_dir / "stellar" / f"{op.pointer}.json")
    if op.mechanism == "rekor":
        return _archive_rekor(session, op, out_dir / "rekor" / f"{op.pointer}.json")
    return "local"


def _archive_contract(contract_id: str, out_dir: Path) -> str:
    wasm_path = out_dir / "contract" / "anchor.wasm"
    if not wasm_path.exists():
        wasm = SorobanServer(RPC_URL).get_contract_wasm(contract_id)
        wasm_path.parent.mkdir(parents=True, exist_ok=True)
        wasm_path.write_bytes(wasm)
    digest = hashlib.sha256(wasm_path.read_bytes()).hexdigest()
    info: JsonObject = {"contractId": contract_id, "network": "testnet", "wasmSha256": digest}
    write_json(out_dir / "contract" / "contract.json", info)
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive public evidence of pilot operations.")
    parser.add_argument("--label", default="pilot-v1")
    parser.add_argument("--ops", type=Path, default=DEFAULT_OPS_CSV)
    parser.add_argument("--contract", default=PILOT_V1_CONTRACT)
    args = parser.parse_args()

    out_dir: Path = REPO_ROOT / "evidence" / args.label
    ops = load_pilot_ops(args.ops)
    session = requests.Session()
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(lambda op: _archive_one(session, op, out_dir), ops))

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome] = counts.get(outcome, 0) + 1
    wasm_digest = _archive_contract(args.contract, out_dir)

    manifest: JsonObject = {
        "label": args.label,
        "opsCsv": args.ops.resolve().relative_to(REPO_ROOT).as_posix(),
        "retrievedAtUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {"horizon": HORIZON_URL, "rekor": REKOR_URL, "sorobanRpc": RPC_URL},
        "stellarTransactions": sum(1 for op in ops if op.mechanism in ("soroban", "classic")),
        "rekorEntries": sum(1 for op in ops if op.mechanism == "rekor"),
        "contractId": args.contract,
        "contractWasmSha256": wasm_digest,
    }
    write_json(out_dir / "manifest.json", manifest)
    print(f"evidence/{args.label}: {counts}; contract wasm sha256 {wasm_digest[:16]}...")


if __name__ == "__main__":
    main()
