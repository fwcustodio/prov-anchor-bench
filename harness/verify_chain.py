"""Rebuilds the artifact chain and verifies it end to end; then demonstrates
that suppressing a link is detected (functional validation of the chain
construction).

Usage: python -m harness.verify_chain
"""

from __future__ import annotations

import secrets as pysecrets
import sys

from .artifacts import build_artifacts
from .prov import build_chain, verify_chain


def main() -> None:
    artifacts = build_artifacts()
    chain = build_chain(
        [a.as_input() for a in artifacts], "prov-anchor-bench-pilot", pysecrets.token_hex(8)
    )

    intact = verify_chain(chain)
    print(
        f"full chain ({len(chain)} links): "
        f"{'VERIFIED' if intact == -1 else f'BROKEN at {intact}'}"
    )

    suppressed = chain[:5] + chain[6:]
    broken = verify_chain(suppressed)
    print(
        "chain with link 5 suppressed: "
        f"{'NOT DETECTED (error)' if broken == -1 else f'break detected at index {broken}'}"
    )

    if intact != -1 or broken == -1:
        sys.exit(1)


if __name__ == "__main__":
    main()
