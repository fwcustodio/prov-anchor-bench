import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

export const ZERO_HASH: string = "0".repeat(64);

/** Minimal W3C PROV-DM style record: entity, activity, agent, plus chain link. */
export interface ProvRecord {
  readonly entity: { readonly id: string; readonly sha256: string };
  readonly activity: { readonly id: string; readonly type: string; readonly endedAtIso: string };
  readonly agent: { readonly id: string };
  readonly used: readonly string[];
  /** SHA-256 (hex) of the previous provenance record in the chain; ZERO_HASH for the first. */
  readonly prev: string;
  /** Run-unique nonce so public log entries never collide across runs. */
  readonly nonce: string;
}

export interface ChainedArtifact {
  readonly artifactId: string;
  readonly artifactSha256: string;
  readonly record: ProvRecord;
  readonly recordSha256: string;
  readonly prevArtifactSha256: string;
}

export function sha256Hex(data: Buffer | string): string {
  return createHash("sha256").update(data).digest("hex");
}

export function sha256OfFile(path: string): string {
  return sha256Hex(readFileSync(path));
}

/** Deterministic serialization: keys sorted at every level. */
export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (typeof value === "object" && value !== null) {
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(record[k])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export interface ArtifactInput {
  readonly id: string;
  readonly sha256: string;
  readonly stepType: string;
  readonly usedIds: readonly string[];
}

/** Builds the chained provenance records for a list of pipeline artifacts, in order. */
export function buildChain(
  artifacts: readonly ArtifactInput[],
  agentId: string,
  runNonce: string,
): ChainedArtifact[] {
  const chain: ChainedArtifact[] = [];
  let prevRecordHash = ZERO_HASH;
  let prevArtifactHash = ZERO_HASH;
  for (const artifact of artifacts) {
    const record: ProvRecord = {
      entity: { id: artifact.id, sha256: artifact.sha256 },
      activity: {
        id: `act-${artifact.id}`,
        type: artifact.stepType,
        endedAtIso: new Date().toISOString(),
      },
      agent: { id: agentId },
      used: artifact.usedIds,
      prev: prevRecordHash,
      nonce: runNonce,
    };
    const recordSha256 = sha256Hex(canonicalJson(record));
    chain.push({
      artifactId: artifact.id,
      artifactSha256: artifact.sha256,
      record,
      recordSha256,
      prevArtifactSha256: prevArtifactHash,
    });
    prevRecordHash = recordSha256;
    prevArtifactHash = artifact.sha256;
  }
  return chain;
}

/**
 * Verifies a chain: every record's hash must match its canonical serialization,
 * and every `prev` must equal the hash of the preceding record. Removing or
 * altering any element breaks the chain. Returns the index of the first broken
 * link, or -1 if the chain verifies.
 */
export function verifyChain(chain: readonly ChainedArtifact[]): number {
  let prevRecordHash = ZERO_HASH;
  for (let i = 0; i < chain.length; i += 1) {
    const link = chain[i];
    if (link === undefined) return i;
    if (link.record.prev !== prevRecordHash) return i;
    if (sha256Hex(canonicalJson(link.record)) !== link.recordSha256) return i;
    prevRecordHash = link.recordSha256;
  }
  return -1;
}
