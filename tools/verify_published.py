"""Independent verification of the published pilot results.

Rebuilds the pipeline artifacts from the official INMET file and checks every
published operation against its public evidence: Stellar transactions
(hash anchored on-chain == hash of the rebuilt artifact), Rekor entries
(Merkle inclusion proof against the published tree root), the local control
logs, the deployed contract bytecode and the medians reported in
docs/resultados-piloto.md.

Offline by default (reads evidence/<label>/); --online re-fetches everything
from Horizon, Rekor and Soroban RPC instead.

Usage:
    python -m tools.fetch_inmet                 # once: official input data
    python -m tools.verify_published            # offline, archived evidence
    python -m tools.verify_published --online   # live public services
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Final

import requests
from stellar_sdk import Address, SorobanServer
from stellar_sdk.xdr import SCVal

from harness.artifacts import build_artifacts
from harness.config import DATA_DIR, MECHANISMS, REKOR_URL, REPO_ROOT, RPC_URL, RUNS_DIR, Mechanism

from .archive_evidence import HORIZON_URL, PILOT_V1_CONTRACT, get_json
from .fetch_inmet import EXPECTED_SHA256
from .jsontypes import (
    JsonObject,
    JsonValue,
    as_object,
    get_bool,
    get_int,
    get_list,
    get_object,
    get_str,
    parse_json,
    read_json,
)
from .pilot_ops import DEFAULT_OPS_CSV, PilotOp, load_pilot_ops

# Medians published in docs/resultados-piloto.md (ms, all windows pooled).
REPORTED_MEDIANS_MS: Final[dict[Mechanism, float]] = {
    "soroban": 4460.0,
    "classic": 4545.0,
    "rekor": 451.0,
    "control": 3.0,
}
# Confirmation must follow submission; generous upper bound for slow ledgers.
_MAX_CONFIRM_DELAY_S: Final[float] = 90.0
_CLOCK_SLACK_S: Final[float] = 2.0
INMET_CSV: Final[Path] = DATA_DIR / "inmet.csv"


@dataclass
class Check:
    name: str
    total: int = 0
    failures: list[str] = field(default_factory=list)

    def record(self, ok: bool, detail: str) -> None:
        self.total += 1
        if not ok:
            self.failures.append(detail)

    @property
    def passed(self) -> int:
        return self.total - len(self.failures)

    @property
    def ok(self) -> bool:
        return self.total > 0 and not self.failures


# ---------------------------------------------------------------- evidence

EvidenceLoader = Callable[[PilotOp], JsonObject]


def offline_loaders(evidence_dir: Path) -> tuple[EvidenceLoader, EvidenceLoader]:
    def stellar(op: PilotOp) -> JsonObject:
        return as_object(read_json(evidence_dir / "stellar" / f"{op.pointer}.json"), op.pointer)

    def rekor(op: PilotOp) -> JsonObject:
        return as_object(read_json(evidence_dir / "rekor" / f"{op.pointer}.json"), op.pointer)

    return stellar, rekor


def online_loaders() -> tuple[EvidenceLoader, EvidenceLoader]:
    session = requests.Session()

    def stellar(op: PilotOp) -> JsonObject:
        transaction = get_json(session, f"{HORIZON_URL}/transactions/{op.pointer}")
        operations = get_json(
            session, f"{HORIZON_URL}/transactions/{op.pointer}/operations?limit=20"
        )
        return {"transaction": transaction, "operations": operations}

    def rekor(op: PilotOp) -> JsonObject:
        return as_object(
            get_json(session, f"{REKOR_URL}/api/v1/log/entries/{op.pointer}"), op.pointer
        )

    return stellar, rekor


# ----------------------------------------------------------------- helpers


def _parse_utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _within_window(submitted: datetime, confirmed: datetime) -> bool:
    delay = (confirmed - submitted).total_seconds()
    return -_CLOCK_SLACK_S <= delay <= _MAX_CONFIRM_DELAY_S


def _operation_records(evidence: JsonObject, context: str) -> list[JsonObject]:
    operations = get_object(evidence, "operations", context)
    embedded = get_object(operations, "_embedded", context)
    return [as_object(item, context) for item in get_list(embedded, "records", context)]


def _soroban_call(record: JsonObject, context: str) -> tuple[str, str, str]:
    """Returns (contract id, function name, anchored artifact hash hex)."""
    parameters = [as_object(item, context) for item in get_list(record, "parameters", context)]
    values = [SCVal.from_xdr(get_str(p, "value", context)) for p in parameters]
    if len(values) < 3 or values[0].address is None or values[1].sym is None:
        raise ValueError(f"{context}: unexpected invoke_host_function parameters")
    contract = Address.from_xdr_sc_address(values[0].address).address
    function = values[1].sym.sc_symbol.decode("utf8")
    artifact = values[2].bytes
    if artifact is None:
        raise ValueError(f"{context}: artifact parameter is not Bytes")
    return contract, function, artifact.sc_bytes.hex()


def _classic_artifact_hash(records: list[JsonObject], context: str) -> str:
    for record in records:
        if get_str(record, "type", context) == "manage_data" and get_str(
            record, "name", context
        ).endswith("-art"):
            return base64.b64decode(get_str(record, "value", context)).hex()
    raise ValueError(f"{context}: no '-art' manageData operation")


def _rfc6962_root(leaf_index: int, tree_size: int, leaf_hash: bytes, path: list[bytes]) -> bytes:
    """Root implied by an RFC 6962/9162 inclusion proof (section 2.1.3.2)."""
    fn, sn = leaf_index, tree_size - 1
    node = leaf_hash
    for sibling in path:
        if sn == 0:
            raise ValueError("inclusion proof longer than the tree allows")
        if fn & 1 or fn == sn:
            node = hashlib.sha256(b"\x01" + sibling + node).digest()
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            node = hashlib.sha256(b"\x01" + node + sibling).digest()
        fn >>= 1
        sn >>= 1
    if sn != 0:
        raise ValueError("inclusion proof shorter than the tree requires")
    return node


# ------------------------------------------------------------------ checks


def check_stellar(
    ops: list[PilotOp],
    artifacts: dict[str, str],
    load: EvidenceLoader,
    contract_id: str,
    checks: dict[str, Check],
) -> None:
    for op in ops:
        if op.mechanism not in ("soroban", "classic") or op.status != "SUCCESS":
            continue
        ctx = f"w{op.window} #{op.op_seq} {op.mechanism} {op.pointer[:12]}"
        try:
            evidence = load(op)
            transaction = get_object(evidence, "transaction", ctx)
            records = _operation_records(evidence, ctx)
        except (OSError, ValueError, requests.RequestException) as error:
            checks["exists"].record(False, f"{ctx}: {error}")
            continue
        checks["exists"].record(get_bool(transaction, "successful", ctx), f"{ctx}: not successful")
        checks["fee"].record(
            get_str(transaction, "fee_charged", ctx) == op.fee_stroops,
            f"{ctx}: fee {get_str(transaction, 'fee_charged', ctx)} != {op.fee_stroops}",
        )
        checks["timing"].record(
            _within_window(op.submitted_at, _parse_utc(get_str(transaction, "created_at", ctx))),
            f"{ctx}: ledger close time inconsistent with submission",
        )
        expected = artifacts.get(op.artifact_id, "")
        if op.mechanism == "soroban":
            contract, function, anchored = _soroban_call(records[0], ctx)
            checks["contract_call"].record(
                contract == contract_id and function == "anchor",
                f"{ctx}: called {contract}.{function}",
            )
        else:
            anchored = _classic_artifact_hash(records, ctx)
        checks["artifact_hash"].record(
            anchored == expected, f"{ctx}: on-chain {anchored[:12]} != rebuilt {expected[:12]}"
        )


def check_rekor(ops: list[PilotOp], load: EvidenceLoader, checks: dict[str, Check]) -> None:
    public_keys: set[str] = set()
    for op in ops:
        if op.mechanism != "rekor" or op.status != "SUCCESS":
            continue
        ctx = f"w{op.window} #{op.op_seq} rekor {op.pointer[:12]}"
        try:
            document = load(op)
        except (OSError, ValueError, requests.RequestException) as error:
            checks["rekor_exists"].record(False, f"{ctx}: {error}")
            continue
        entry = get_object(document, op.pointer, ctx)
        checks["rekor_exists"].record(
            f"logIndex={get_int(entry, 'logIndex', ctx)}" == op.note, f"{ctx}: logIndex mismatch"
        )
        checks["rekor_timing"].record(
            _within_window(
                op.submitted_at,
                datetime.fromtimestamp(get_int(entry, "integratedTime", ctx), tz=timezone.utc),
            ),
            f"{ctx}: integratedTime inconsistent with submission",
        )
        body_bytes = base64.b64decode(get_str(entry, "body", ctx))
        body: JsonValue = parse_json(body_bytes.decode("utf8"))
        spec = get_object(as_object(body, ctx), "spec", ctx)
        signature = get_object(spec, "signature", ctx)
        public_keys.add(get_str(get_object(signature, "publicKey", ctx), "content", ctx))

        proof = get_object(get_object(entry, "verification", ctx), "inclusionProof", ctx)
        leaf_hash = hashlib.sha256(b"\x00" + body_bytes).digest()
        path = [bytes.fromhex(str(item)) for item in get_list(proof, "hashes", ctx)]
        root_hex = get_str(proof, "rootHash", ctx)
        try:
            root = _rfc6962_root(
                get_int(proof, "logIndex", ctx), get_int(proof, "treeSize", ctx), leaf_hash, path
            )
            valid = (
                root.hex() == root_hex
                and op.pointer.endswith(leaf_hash.hex())
                and base64.b64encode(bytes.fromhex(root_hex)).decode("ascii")
                in get_str(proof, "checkpoint", ctx)
            )
        except ValueError as error:
            valid = False
            ctx = f"{ctx}: {error}"
        checks["rekor_inclusion"].record(valid, f"{ctx}: inclusion proof does not verify")
    checks["rekor_key"].record(len(public_keys) == 1, f"{len(public_keys)} distinct signing keys")


def check_control(ops: list[PilotOp], artifacts: dict[str, str], checks: dict[str, Check]) -> None:
    windows = sorted({op.window for op in ops})
    for window in windows:
        expected = [
            artifacts.get(op.artifact_id, "")
            for op in sorted(ops, key=lambda o: o.op_seq)
            if op.window == window and op.mechanism == "control" and op.status == "SUCCESS"
        ]
        matched = False
        for log_path in sorted(RUNS_DIR.glob(f"control-log-w{window}-*.jsonl")):
            logged: list[str] = []
            for line in log_path.read_text(encoding="utf8").splitlines():
                logged.append(get_str(as_object(parse_json(line), log_path.name), "artifact", log_path.name))
            if logged == expected:
                matched = True
        checks["control_log"].record(matched, f"window {window}: no control log matches the CSV")


def check_contract(evidence_dir: Path, online: bool, contract_id: str, checks: dict[str, Check]) -> None:
    info = as_object(read_json(evidence_dir / "contract" / "contract.json"), "contract.json")
    archived = (evidence_dir / "contract" / "anchor.wasm").read_bytes()
    digest = hashlib.sha256(archived).hexdigest()
    checks["contract_wasm"].record(
        digest == get_str(info, "wasmSha256", "contract.json")
        and get_str(info, "contractId", "contract.json") == contract_id,
        "archived wasm does not match contract.json",
    )
    if online:
        live = SorobanServer(RPC_URL).get_contract_wasm(contract_id)
        checks["contract_wasm"].record(live == archived, "deployed wasm differs from archive")


def check_medians(ops: list[PilotOp], checks: dict[str, Check]) -> None:
    for mechanism in MECHANISMS:
        values = [op.latency_ms for op in ops if op.mechanism == mechanism and op.status == "SUCCESS"]
        observed = statistics.median(values)
        reported = REPORTED_MEDIANS_MS[mechanism]
        checks["medians"].record(
            round(observed) == round(reported) or abs(observed - reported) <= 1.0,
            f"{mechanism}: recomputed {observed:.1f} ms vs reported {reported:.0f} ms",
        )


# -------------------------------------------------------------------- main

_LABELS: Final[dict[str, str]] = {
    "input": "Arquivo de entrada = arquivo oficial do INMET (SHA-256)",
    "exists": "Transações Stellar existem e foram bem-sucedidas",
    "fee": "Taxa cobrada on-chain = taxa registrada no CSV",
    "timing": "Horário de fechamento do ledger consistente com o envio",
    "contract_call": "Soroban: invocação de anchor() no contrato do piloto",
    "artifact_hash": "Hash ancorado on-chain = hash do artefato reconstruído",
    "rekor_exists": "Rekor: entrada existe e logIndex = CSV",
    "rekor_timing": "Rekor: integratedTime consistente com o envio",
    "rekor_inclusion": "Rekor: prova de inclusão Merkle (RFC 6962) válida",
    "rekor_key": "Rekor: uma única chave de assinatura do piloto",
    "control_log": "Controle: log local por janela = CSV",
    "contract_wasm": "Contrato: bytecode arquivado (e implantado, se --online)",
    "medians": "Medianas recalculadas = medianas publicadas no relatório",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify published pilot results.")
    parser.add_argument("--label", default="pilot-v1")
    parser.add_argument("--ops", type=Path, default=DEFAULT_OPS_CSV)
    parser.add_argument("--contract", default=PILOT_V1_CONTRACT)
    parser.add_argument("--online", action="store_true", help="re-fetch from public services")
    args = parser.parse_args()
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    checks: dict[str, Check] = {key: Check(label) for key, label in _LABELS.items()}
    if not INMET_CSV.exists():
        print("Arquivo do INMET ausente: rode antes  python -m tools.fetch_inmet", file=sys.stderr)
        sys.exit(2)
    input_digest = hashlib.sha256(INMET_CSV.read_bytes()).hexdigest()
    checks["input"].record(input_digest == EXPECTED_SHA256, f"input SHA-256 {input_digest}")

    artifacts = {a.id: a.sha256 for a in build_artifacts()}
    ops = load_pilot_ops(args.ops)
    evidence_dir: Path = REPO_ROOT / "evidence" / args.label
    stellar_loader, rekor_loader = (
        online_loaders() if args.online else offline_loaders(evidence_dir)
    )

    check_stellar(ops, artifacts, stellar_loader, args.contract, checks)
    check_rekor(ops, rekor_loader, checks)
    check_control(ops, artifacts, checks)
    check_contract(evidence_dir, args.online, args.contract, checks)
    check_medians(ops, checks)

    mode = "online (serviços públicos)" if args.online else f"offline (evidence/{args.label})"
    print(f"Verificação dos resultados publicados: {args.label}, modo {mode}")
    print(f"{len(ops)} operações no CSV\n")
    all_ok = True
    for check in checks.values():
        status = "OK   " if check.ok else "FALHA"
        all_ok = all_ok and check.ok
        print(f"  [{status}] {check.passed:>3}/{check.total:<3} {check.name}")
        for failure in check.failures[:5]:
            print(f"           - {failure}")
    print("\nRESULTADO: " + ("APROVADO" if all_ok else "REPROVADO"))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
