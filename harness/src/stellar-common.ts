import { Keypair, Transaction, rpc } from "@stellar/stellar-sdk";
import { nowMs, sleep } from "./measure.js";

export interface ConfirmedResult {
  readonly latencyMs: number;
  readonly feeStroops: string;
  readonly txHash: string;
  readonly ledger: number;
}

/**
 * Submits a signed transaction through Soroban RPC and polls until it is
 * included in a ledger. Both Stellar mechanisms (contract invocation and
 * classic manageData) go through this same path so their instrumentation
 * is symmetric: latency = sendTransaction() call until getTransaction()
 * first reports SUCCESS.
 */
export async function submitAndConfirm(
  server: rpc.Server,
  tx: Transaction,
  keypair: Keypair,
  timeoutMs = 60_000,
): Promise<ConfirmedResult> {
  tx.sign(keypair);
  const t0 = nowMs();
  const send = await server.sendTransaction(tx);
  if (send.status === "ERROR") {
    throw new Error(`sendTransaction ERROR: ${JSON.stringify(send.errorResult ?? send.status)}`);
  }
  const deadline = t0 + timeoutMs;
  for (;;) {
    const response = await server.getTransaction(send.hash);
    if (response.status === rpc.Api.GetTransactionStatus.SUCCESS) {
      const t1 = nowMs();
      return {
        latencyMs: t1 - t0,
        feeStroops: response.resultXdr.feeCharged().toString(),
        txHash: send.hash,
        ledger: response.ledger,
      };
    }
    if (response.status === rpc.Api.GetTransactionStatus.FAILED) {
      throw new Error(`transaction FAILED: ${send.hash}`);
    }
    if (nowMs() > deadline) {
      throw new Error(`confirmation timeout after ${timeoutMs} ms: ${send.hash}`);
    }
    await sleep(250);
  }
}
