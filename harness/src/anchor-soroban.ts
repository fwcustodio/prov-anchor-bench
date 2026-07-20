import { BASE_FEE, Contract, Keypair, TransactionBuilder, rpc, xdr } from "@stellar/stellar-sdk";
import { NETWORK_PASSPHRASE, RPC_URL } from "./config.js";
import { submitAndConfirm, type ConfirmedResult } from "./stellar-common.js";
import type { ChainedArtifact } from "./prov.js";

export class SorobanAnchor {
  private readonly server: rpc.Server;
  private readonly contract: Contract;
  private readonly keypair: Keypair;

  constructor(contractId: string, secret: string) {
    this.server = new rpc.Server(RPC_URL);
    this.contract = new Contract(contractId);
    this.keypair = Keypair.fromSecret(secret);
  }

  /** Anchors one chained artifact by invoking the contract's `anchor` function. */
  async anchor(link: ChainedArtifact): Promise<ConfirmedResult> {
    const account = await this.server.getAccount(this.keypair.publicKey());
    const operation = this.contract.call(
      "anchor",
      xdr.ScVal.scvBytes(Buffer.from(link.artifactSha256, "hex")),
      xdr.ScVal.scvBytes(Buffer.from(link.recordSha256, "hex")),
      xdr.ScVal.scvBytes(Buffer.from(link.prevArtifactSha256, "hex")),
    );
    const built = new TransactionBuilder(account, {
      fee: BASE_FEE,
      networkPassphrase: NETWORK_PASSPHRASE,
    })
      .addOperation(operation)
      .setTimeout(60)
      .build();
    const prepared = await this.server.prepareTransaction(built);
    return submitAndConfirm(this.server, prepared, this.keypair);
  }
}
