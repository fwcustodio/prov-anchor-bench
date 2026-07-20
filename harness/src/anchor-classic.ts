import { BASE_FEE, Keypair, Operation, TransactionBuilder, rpc } from "@stellar/stellar-sdk";
import { NETWORK_PASSPHRASE, RPC_URL } from "./config.js";
import { submitAndConfirm, type ConfirmedResult } from "./stellar-common.js";
import type { ChainedArtifact } from "./prov.js";

export class ClassicAnchor {
  private readonly server: rpc.Server;
  private readonly keypair: Keypair;
  private counter = 0;

  constructor(secret: string) {
    this.server = new rpc.Server(RPC_URL);
    this.keypair = Keypair.fromSecret(secret);
  }

  /**
   * Anchors one chained artifact with a classic `manageData` operation:
   * the entry name carries a per-run sequence, the 32-byte value is the
   * artifact hash. The provenance-record hash is written in a second data
   * entry within the same transaction so both hashes land on-chain.
   */
  async anchor(link: ChainedArtifact): Promise<ConfirmedResult> {
    this.counter += 1;
    const name = `a${String(this.counter).padStart(5, "0")}`;
    const account = await this.server.getAccount(this.keypair.publicKey());
    const tx = new TransactionBuilder(account, {
      fee: BASE_FEE,
      networkPassphrase: NETWORK_PASSPHRASE,
    })
      .addOperation(
        Operation.manageData({ name: `${name}-art`, value: Buffer.from(link.artifactSha256, "hex") }),
      )
      .addOperation(
        Operation.manageData({ name: `${name}-prv`, value: Buffer.from(link.recordSha256, "hex") }),
      )
      .setTimeout(60)
      .build();
    return submitAndConfirm(this.server, tx, this.keypair);
  }
}
