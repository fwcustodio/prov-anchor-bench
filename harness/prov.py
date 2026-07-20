"""Minimal W3C PROV-DM style records and the hash chain over pipeline artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Sequence

ZERO_HASH: Final[str] = "0" * 64


def sha256_hex(data: bytes | str) -> str:
    payload = data.encode("utf8") if isinstance(data, str) else data
    return hashlib.sha256(payload).hexdigest()


def sha256_of_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def canonical_json(value: object) -> str:
    """Deterministic serialization: keys sorted at every level, no whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class ArtifactInput:
    """A pipeline artifact to be chained."""

    id: str
    sha256: str
    step_type: str
    used_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChainedArtifact:
    """One link of the provenance chain."""

    artifact_id: str
    artifact_sha256: str
    record: dict[str, object]
    record_sha256: str
    prev_artifact_sha256: str


def build_chain(
    artifacts: Sequence[ArtifactInput], agent_id: str, run_nonce: str
) -> list[ChainedArtifact]:
    """Builds the chained provenance records for pipeline artifacts, in order."""
    chain: list[ChainedArtifact] = []
    prev_record_hash = ZERO_HASH
    prev_artifact_hash = ZERO_HASH
    for artifact in artifacts:
        record: dict[str, object] = {
            "entity": {"id": artifact.id, "sha256": artifact.sha256},
            "activity": {
                "id": f"act-{artifact.id}",
                "type": artifact.step_type,
                "endedAtIso": datetime.now(timezone.utc).isoformat(),
            },
            "agent": {"id": agent_id},
            "used": list(artifact.used_ids),
            "prev": prev_record_hash,
            "nonce": run_nonce,
        }
        record_sha256 = sha256_hex(canonical_json(record))
        chain.append(
            ChainedArtifact(
                artifact_id=artifact.id,
                artifact_sha256=artifact.sha256,
                record=record,
                record_sha256=record_sha256,
                prev_artifact_sha256=prev_artifact_hash,
            )
        )
        prev_record_hash = record_sha256
        prev_artifact_hash = artifact.sha256
    return chain


def verify_chain(chain: Sequence[ChainedArtifact]) -> int:
    """Returns the index of the first broken link, or -1 if the chain verifies.

    Every record's hash must match its canonical serialization and every
    ``prev`` must equal the hash of the preceding record, so removing or
    altering any element breaks the chain.
    """
    prev_record_hash = ZERO_HASH
    for index, link in enumerate(chain):
        if link.record.get("prev") != prev_record_hash:
            return index
        if sha256_hex(canonical_json(link.record)) != link.record_sha256:
            return index
        prev_record_hash = link.record_sha256
    return -1
