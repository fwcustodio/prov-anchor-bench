"""Isolated local cryptographic primitive.

Time to SHA-256 hash and to ECDSA-P256-sign each artifact, measured
off-network: the deterministic reference against which every remote
mechanism's network cost is compared.

Usage: python -m harness.local_primitive [--reps 100]
"""

from __future__ import annotations

import argparse
import hashlib
from typing import Final

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from .artifacts import build_artifacts
from .config import RUNS_DIR
from .measure import median, now_ms

_CSV_PATH: Final = RUNS_DIR / "local-primitive.csv"
_HEADER: Final[str] = "artifact_id;bytes;hash_ms_median;sign_ms_median;reps"


def main() -> None:
    parser = argparse.ArgumentParser(description="Local crypto primitive timing.")
    parser.add_argument("--reps", type=int, default=100)
    args = parser.parse_args()

    key = ec.generate_private_key(ec.SECP256R1())
    artifacts = build_artifacts()

    if not _CSV_PATH.exists():
        _CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CSV_PATH.write_text(f"{_HEADER}\n", encoding="utf8")

    with _CSV_PATH.open("a", encoding="utf8") as handle:
        for artifact in artifacts:
            content = artifact.path.read_bytes()
            hash_times: list[float] = []
            sign_times: list[float] = []
            for _ in range(args.reps):
                t0 = now_ms()
                hashlib.sha256(content).digest()
                t1 = now_ms()
                key.sign(content, ec.ECDSA(hashes.SHA256()))
                t2 = now_ms()
                hash_times.append(t1 - t0)
                sign_times.append(t2 - t1)
            handle.write(
                f"{artifact.id};{len(content)};{median(hash_times):.4f};"
                f"{median(sign_times):.4f};{args.reps}\n"
            )
            print(
                f"{artifact.id:<12} {len(content):>8} B  "
                f"hash {median(hash_times):.3f} ms  sign {median(sign_times):.3f} ms"
            )
    print(f"\nRows written to {_CSV_PATH}")


if __name__ == "__main__":
    main()
