import { randomBytes } from "node:crypto";
import { join } from "node:path";
import { MECHANISMS, RUNS_DIR, loadSecrets, type Mechanism } from "./config.js";
import { buildArtifacts } from "./artifacts.js";
import { buildChain, type ChainedArtifact } from "./prov.js";
import { appendOpRecord, seededShuffle, type OpRecord } from "./measure.js";
import { SorobanAnchor } from "./anchor-soroban.js";
import { ClassicAnchor } from "./anchor-classic.js";
import { RekorAnchor } from "./anchor-rekor.js";
import { ControlAnchor } from "./anchor-control.js";

/**
 * Runs one measurement window: K operations per mechanism, in balanced
 * randomized order (shuffled blocks of the 4 mechanisms), writing one CSV
 * row per confirmed operation.
 *
 * Usage:
 *   tsx src/run-pilot.ts --smoke               (K=3, window 0)
 *   tsx src/run-pilot.ts --window 1 [--k 13]
 */

interface Args {
  readonly smoke: boolean;
  readonly window: number;
  readonly k: number;
}

function parseArgs(argv: readonly string[]): Args {
  const smoke = argv.includes("--smoke");
  const windowIndex = argv.indexOf("--window");
  const kIndex = argv.indexOf("--k");
  const window = windowIndex >= 0 ? Number(argv[windowIndex + 1] ?? "0") : smoke ? 0 : 1;
  const k = kIndex >= 0 ? Number(argv[kIndex + 1] ?? "13") : smoke ? 3 : 13;
  if (!Number.isInteger(window) || !Number.isInteger(k) || k <= 0) {
    throw new Error("invalid --window/--k");
  }
  return { smoke, window, k };
}

function median(values: readonly number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const a = sorted[mid];
  const b = sorted[sorted.length % 2 === 0 ? mid - 1 : mid];
  if (a === undefined || b === undefined) return Number.NaN;
  return (a + b) / 2;
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const secrets = loadSecrets();
  const runNonce = randomBytes(8).toString("hex");
  const csvPath = join(RUNS_DIR, args.smoke ? "smoke-ops.csv" : "pilot-ops.csv");

  const artifacts = buildArtifacts();
  const chain = buildChain(
    artifacts.map(({ id, sha256, stepType, usedIds }) => ({ id, sha256, stepType, usedIds })),
    "prov-anchor-bench-pilot",
    runNonce,
  );

  const soroban = new SorobanAnchor(secrets.contractId, secrets.sorobanSecret);
  const classic = new ClassicAnchor(secrets.classicSecret);
  const rekor = new RekorAnchor();
  const control = new ControlAnchor(`w${args.window}-${runNonce}`);

  // K blocks, each containing the 4 mechanisms in shuffled order.
  const schedule: Mechanism[] = [];
  for (let block = 0; block < args.k; block += 1) {
    schedule.push(...seededShuffle(MECHANISMS, args.window * 1000 + block));
  }

  const latencies = new Map<Mechanism, number[]>(MECHANISMS.map((m) => [m, []]));
  let opSeq = 0;
  for (const mechanism of schedule) {
    const link: ChainedArtifact | undefined = chain[opSeq % chain.length];
    if (link === undefined) throw new Error("empty chain");
    opSeq += 1;
    const submittedAtIso = new Date().toISOString();
    let record: OpRecord;
    try {
      if (mechanism === "soroban") {
        const r = await soroban.anchor(link);
        record = row(args.window, opSeq, mechanism, link, submittedAtIso, r.latencyMs, r.feeStroops, r.txHash, "");
      } else if (mechanism === "classic") {
        const r = await classic.anchor(link);
        record = row(args.window, opSeq, mechanism, link, submittedAtIso, r.latencyMs, r.feeStroops, r.txHash, "");
      } else if (mechanism === "rekor") {
        const r = await rekor.anchor(link);
        record = row(args.window, opSeq, mechanism, link, submittedAtIso, r.latencyMs, "", r.uuid, `logIndex=${r.logIndex}`);
      } else {
        const r = control.anchor(link);
        record = row(args.window, opSeq, mechanism, link, submittedAtIso, r.latencyMs, "", `offset=${r.offset}`, "");
      }
      latencies.get(mechanism)?.push(record.latencyMs);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      record = {
        window: args.window,
        opSeq,
        mechanism,
        artifactId: link.artifactId,
        submittedAtIso,
        latencyMs: -1,
        feeStroops: "",
        pointer: "",
        status: "FAILED",
        note: message.slice(0, 160),
      };
    }
    appendOpRecord(csvPath, record);
    console.log(
      `[w${args.window} ${String(opSeq).padStart(3, "0")}] ${mechanism.padEnd(7)} ${record.status} ${
        record.latencyMs >= 0 ? `${record.latencyMs.toFixed(0)} ms` : ""
      } ${record.pointer.slice(0, 20)}`,
    );
  }

  console.log(`\nWindow ${args.window} summary (median latency):`);
  for (const mechanism of MECHANISMS) {
    const values = latencies.get(mechanism) ?? [];
    console.log(`  ${mechanism.padEnd(7)} n=${values.length}  median=${median(values).toFixed(0)} ms`);
  }
  console.log(`\nRows appended to ${csvPath}`);
}

function row(
  window: number,
  opSeq: number,
  mechanism: Mechanism,
  link: ChainedArtifact,
  submittedAtIso: string,
  latencyMs: number,
  feeStroops: string,
  pointer: string,
  note: string,
): OpRecord {
  return {
    window,
    opSeq,
    mechanism,
    artifactId: link.artifactId,
    submittedAtIso,
    latencyMs,
    feeStroops,
    pointer,
    status: "SUCCESS",
    note,
  };
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
