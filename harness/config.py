"""Shared configuration: endpoints, paths and disposable pilot secrets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

HARNESS_ROOT: Final[Path] = Path(__file__).resolve().parent
REPO_ROOT: Final[Path] = HARNESS_ROOT.parent

RPC_URL: Final[str] = "https://soroban-testnet.stellar.org"
FRIENDBOT_URL: Final[str] = "https://friendbot.stellar.org"
REKOR_URL: Final[str] = "https://rekor.sigstore.dev"
NETWORK_PASSPHRASE: Final[str] = "Test SDF Network ; September 2015"

ARTIFACTS_DIR: Final[Path] = HARNESS_ROOT / "artifacts"
DATA_DIR: Final[Path] = HARNESS_ROOT / "data"
RUNS_DIR: Final[Path] = REPO_ROOT / "analysis" / "results"

_SECRETS_PATH: Final[Path] = HARNESS_ROOT / ".pilot-secrets.json"

Mechanism = Literal["soroban", "classic", "rekor", "control"]
MECHANISMS: Final[tuple[Mechanism, ...]] = ("soroban", "classic", "rekor", "control")


@dataclass(frozen=True)
class PilotSecrets:
    """Disposable testnet secrets and the deployed contract id."""

    soroban_secret: str
    classic_secret: str
    contract_id: str


def load_secrets() -> PilotSecrets:
    if not _SECRETS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {_SECRETS_PATH}. Create it with "
            '{"sorobanSecret":"S...","classicSecret":"S...","contractId":"C..."} '
            "(disposable testnet keys only)."
        )
    raw: object = json.loads(_SECRETS_PATH.read_text(encoding="utf8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{_SECRETS_PATH} does not contain a JSON object.")
    soroban_secret = raw.get("sorobanSecret")
    classic_secret = raw.get("classicSecret")
    contract_id = raw.get("contractId")
    if (
        not isinstance(soroban_secret, str)
        or not isinstance(classic_secret, str)
        or not isinstance(contract_id, str)
    ):
        raise ValueError(f"{_SECRETS_PATH} does not match the expected shape.")
    return PilotSecrets(
        soroban_secret=soroban_secret,
        classic_secret=classic_secret,
        contract_id=contract_id,
    )
