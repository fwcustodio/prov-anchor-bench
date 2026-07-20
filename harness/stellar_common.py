"""Shared submit-and-confirm path for both Stellar mechanisms.

Contract invocations and classic manageData operations go through the same
RPC submission and polling code so their instrumentation is symmetric:
latency = send_transaction() call until get_transaction() first reports
SUCCESS.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from stellar_sdk import Keypair, SorobanServer, TransactionEnvelope
from stellar_sdk.soroban_rpc import GetTransactionStatus, SendTransactionStatus
from stellar_sdk.xdr import TransactionResult

from .measure import now_ms


@dataclass(frozen=True)
class ConfirmedResult:
    latency_ms: float
    fee_stroops: str
    tx_hash: str
    ledger: int


def _fee_charged(result_xdr: str | None) -> str:
    if result_xdr is None:
        return ""
    try:
        return str(TransactionResult.from_xdr(result_xdr).fee_charged.int64)
    except Exception:
        return ""


def submit_and_confirm(
    server: SorobanServer,
    envelope: TransactionEnvelope,
    keypair: Keypair,
    timeout_ms: float = 60_000.0,
) -> ConfirmedResult:
    envelope.sign(keypair)
    t0 = now_ms()
    send = server.send_transaction(envelope)
    if send.status == SendTransactionStatus.ERROR:
        raise RuntimeError(f"send_transaction ERROR: {send.error_result_xdr}")
    deadline = t0 + timeout_ms
    while True:
        response = server.get_transaction(send.hash)
        if response.status == GetTransactionStatus.SUCCESS:
            t1 = now_ms()
            ledger = response.ledger if response.ledger is not None else -1
            return ConfirmedResult(
                latency_ms=t1 - t0,
                fee_stroops=_fee_charged(response.result_xdr),
                tx_hash=send.hash,
                ledger=ledger,
            )
        if response.status == GetTransactionStatus.FAILED:
            raise RuntimeError(f"transaction FAILED: {send.hash}")
        if now_ms() > deadline:
            raise RuntimeError(f"confirmation timeout after {timeout_ms:.0f} ms: {send.hash}")
        time.sleep(0.25)
