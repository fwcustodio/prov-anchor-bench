"""Rekor mechanism: anchors as ``hashedrekord`` entries in the public log.

The signed payload is the canonical provenance record (which embeds the
artifact hash and the chain link), signed with a pilot-only ECDSA P-256 key
— the canonical hashedrekord combination, verifiable by Rekor against the
submitted digest alone. Latency = POST until the 201 response that confirms
inclusion.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Final

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .config import HARNESS_ROOT, REKOR_URL
from .measure import now_ms
from .prov import ChainedArtifact, canonical_json

_KEY_PATH: Final = HARNESS_ROOT / ".rekor-key.pem"


@dataclass(frozen=True)
class RekorResult:
    latency_ms: float
    uuid: str
    log_index: int


def _load_or_create_key() -> ec.EllipticCurvePrivateKey:
    if _KEY_PATH.exists():
        loaded = serialization.load_pem_private_key(_KEY_PATH.read_bytes(), password=None)
        if not isinstance(loaded, ec.EllipticCurvePrivateKey):
            raise TypeError(f"{_KEY_PATH} is not an EC private key")
        return loaded
    key = ec.generate_private_key(ec.SECP256R1())
    _KEY_PATH.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return key


def _extract_entry(body: object) -> tuple[str, int]:
    if not isinstance(body, dict) or not body:
        raise ValueError("unexpected Rekor response shape")
    uuid, entry = next(iter(body.items()))
    log_index = -1
    if isinstance(entry, dict):
        candidate = entry.get("logIndex")
        if isinstance(candidate, int):
            log_index = candidate
    return str(uuid), log_index


class RekorAnchor:
    def __init__(self) -> None:
        self._key = _load_or_create_key()
        public_pem = self._key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self._public_b64 = base64.b64encode(public_pem).decode("ascii")
        self._session = requests.Session()

    def anchor(self, link: ChainedArtifact) -> RekorResult:
        payload = canonical_json(link.record).encode("utf8")
        digest = hashlib.sha256(payload).hexdigest()
        signature = self._key.sign(payload, ec.ECDSA(hashes.SHA256()))
        body = {
            "apiVersion": "0.0.1",
            "kind": "hashedrekord",
            "spec": {
                "data": {"hash": {"algorithm": "sha256", "value": digest}},
                "signature": {
                    "content": base64.b64encode(signature).decode("ascii"),
                    "publicKey": {"content": self._public_b64},
                },
            },
        }
        t0 = now_ms()
        response = self._session.post(
            f"{REKOR_URL}/api/v1/log/entries",
            json=body,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        t1 = now_ms()
        if response.status_code != 201:
            raise RuntimeError(
                f"Rekor upload failed ({response.status_code}): {response.text[:200]}"
            )
        uuid, log_index = _extract_entry(response.json())
        return RekorResult(latency_ms=t1 - t0, uuid=uuid, log_index=log_index)
