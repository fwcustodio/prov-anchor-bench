import { appendFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

/** One measured anchoring operation. */
export interface OpRecord {
  readonly window: number;
  readonly opSeq: number;
  readonly mechanism: string;
  readonly artifactId: string;
  readonly submittedAtIso: string;
  readonly latencyMs: number;
  /** Fee charged in stroops for Stellar mechanisms; empty otherwise. */
  readonly feeStroops: string;
  /** Transaction hash, Rekor UUID or local offset — the public verification pointer. */
  readonly pointer: string;
  readonly status: "SUCCESS" | "FAILED";
  readonly note: string;
}

const HEADER =
  "window;op_seq;mechanism;artifact_id;submitted_at_iso;latency_ms;fee_stroops;pointer;status;note";

export function appendOpRecord(csvPath: string, record: OpRecord): void {
  if (!existsSync(csvPath)) {
    mkdirSync(dirname(csvPath), { recursive: true });
    writeFileSync(csvPath, `${HEADER}\n`, "utf8");
  }
  const line = [
    record.window,
    record.opSeq,
    record.mechanism,
    record.artifactId,
    record.submittedAtIso,
    record.latencyMs.toFixed(1),
    record.feeStroops,
    record.pointer,
    record.status,
    record.note.replaceAll(";", ","),
  ].join(";");
  appendFileSync(csvPath, `${line}\n`, "utf8");
}

/** Milliseconds with sub-ms precision from the monotonic clock. */
export function nowMs(): number {
  return Number(process.hrtime.bigint()) / 1e6;
}

export async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

/** Fisher-Yates shuffle with a deterministic LCG so runs are reproducible per seed. */
export function seededShuffle<T>(items: readonly T[], seed: number): T[] {
  const result = [...items];
  let state = seed >>> 0;
  const next = (): number => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
  for (let i = result.length - 1; i > 0; i -= 1) {
    const j = Math.floor(next() * (i + 1));
    const a = result[i];
    const b = result[j];
    if (a !== undefined && b !== undefined) {
      result[i] = b;
      result[j] = a;
    }
  }
  return result;
}
