"""Soroban mechanism: anchors by invoking the contract's ``anchor`` function."""

from __future__ import annotations

from stellar_sdk import Keypair, SorobanServer, TransactionBuilder, scval

from .config import NETWORK_PASSPHRASE, RPC_URL
from .prov import ChainedArtifact
from .stellar_common import ConfirmedResult, submit_and_confirm


class SorobanAnchor:
    def __init__(self, contract_id: str, secret: str) -> None:
        self._server = SorobanServer(RPC_URL)
        self._contract_id = contract_id
        self._keypair = Keypair.from_secret(secret)

    def anchor(self, link: ChainedArtifact) -> ConfirmedResult:
        account = self._server.load_account(self._keypair.public_key)
        envelope = (
            TransactionBuilder(
                source_account=account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100,
            )
            .append_invoke_contract_function_op(
                contract_id=self._contract_id,
                function_name="anchor",
                parameters=[
                    scval.to_bytes(bytes.fromhex(link.artifact_sha256)),
                    scval.to_bytes(bytes.fromhex(link.record_sha256)),
                    scval.to_bytes(bytes.fromhex(link.prev_artifact_sha256)),
                ],
            )
            .set_timeout(60)
            .build()
        )
        prepared = self._server.prepare_transaction(envelope)
        return submit_and_confirm(self._server, prepared, self._keypair)
