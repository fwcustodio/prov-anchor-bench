import { createHash, createPrivateKey, createPublicKey, generateKeyPairSync, sign, type KeyObject } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { HARNESS_ROOT, REKOR_URL } from "./config.js";
import { canonicalJson, type ChainedArtifact } from "./prov.js";
import { nowMs } from "./measure.js";

const KEY_PATH: string = join(HARNESS_ROOT, ".rekor-key.pem");

export interface RekorResult {
  readonly latencyMs: number;
  readonly uuid: string;
  readonly logIndex: number;
}

function loadOrCreateKey(): KeyObject {
  if (existsSync(KEY_PATH)) {
    return createPrivateKey(readFileSync(KEY_PATH, "utf8"));
  }
  // ECDSA P-256 with SHA-256 is the canonical hashedrekord combination:
  // Rekor can verify the signature against the submitted digest alone.
  const { privateKey } = generateKeyPairSync("ec", { namedCurve: "P-256" });
  writeFileSync(KEY_PATH, privateKey.export({ type: "pkcs8", format: "pem" }).toString(), "utf8");
  return privateKey;
}

function extractEntry(body: unknown): { uuid: string; logIndex: number } {
  if (typeof body !== "object" || body === null) throw new Error("unexpected Rekor response shape");
  const entries = Object.entries(body as Record<string, unknown>);
  const first = entries[0];
  if (first === undefined) throw new Error("empty Rekor response");
  const [uuid, entry] = first;
  let logIndex = -1;
  if (typeof entry === "object" && entry !== null) {
    const candidate = (entry as Record<string, unknown>)["logIndex"];
    if (typeof candidate === "number") logIndex = candidate;
  }
  return { uuid, logIndex };
}

export class RekorAnchor {
  private readonly privateKey: KeyObject;
  private readonly publicPem: string;

  constructor() {
    this.privateKey = loadOrCreateKey();
    this.publicPem = createPublicKey(this.privateKey)
      .export({ type: "spki", format: "pem" })
      .toString();
  }

  /**
   * Anchors one chained artifact as a `hashedrekord` entry in the public
   * Rekor transparency log: the signed payload is the canonical provenance
   * record (which embeds the artifact hash and the chain link), signed with
   * a pilot-only ECDSA P-256 key. Latency = POST until the 201 response
   * that confirms inclusion.
   */
  async anchor(link: ChainedArtifact): Promise<RekorResult> {
    const payload = Buffer.from(canonicalJson(link.record), "utf8");
    const digest = createHash("sha256").update(payload).digest("hex");
    const signature = sign("sha256", payload, { key: this.privateKey, dsaEncoding: "der" });
    const body = {
      apiVersion: "0.0.1",
      kind: "hashedrekord",
      spec: {
        data: { hash: { algorithm: "sha256", value: digest } },
        signature: {
          content: signature.toString("base64"),
          publicKey: { content: Buffer.from(this.publicPem, "utf8").toString("base64") },
        },
      },
    };
    const t0 = nowMs();
    const response = await fetch(`${REKOR_URL}/api/v1/log/entries`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    const t1 = nowMs();
    if (response.status !== 201) {
      const text = await response.text();
      throw new Error(`Rekor upload failed (${response.status}): ${text.slice(0, 200)}`);
    }
    const parsed: unknown = await response.json();
    const { uuid, logIndex } = extractEntry(parsed);
    return { latencyMs: t1 - t0, uuid, logIndex };
  }
}
