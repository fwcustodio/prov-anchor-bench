"""Classic Stellar mechanism: anchors with ``manageData`` operations.

The entry name carries a per-run sequence; the 32-byte values are the
artifact hash and the provenance-record hash, written in one transaction so
both hashes land on-chain.
"""

from __future__ import annotations

from stellar_sdk import Keypair, SorobanServer, TransactionBuilder

from .config import NETWORK_PASSPHRASE, RPC_URL
from .prov import ChainedArtifact
from .stellar_common import ConfirmedResult, submit_and_confirm


class ClassicAnchor:
    def __init__(self, secret: str) -> None:
        self._server = SorobanServer(RPC_URL)
        self._keypair = Keypair.from_secret(secret)
        self._counter = 0

    def anchor(self, link: ChainedArtifact) -> ConfirmedResult:
        self._counter += 1
        name = f"a{self._counter:05d}"
        account = self._server.load_account(self._keypair.public_key)
        envelope = (
            TransactionBuilder(
                source_account=account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100,
            )
            .append_manage_data_op(
                data_name=f"{name}-art", data_value=bytes.fromhex(link.artifact_sha256)
            )
            .append_manage_data_op(
                data_name=f"{name}-prv", data_value=bytes.fromhex(link.record_sha256)
            )
            .set_timeout(60)
            .build()
        )
        return submit_and_confirm(self._server, envelope, self._keypair)
