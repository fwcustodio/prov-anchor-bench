import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { RUNS_DIR } from "./config.js";
import { buildArtifacts } from "./artifacts.js";
import { nowMs } from "./measure.js";

/**
 * Isolated local cryptographic primitive: time to SHA-256 hash and to
 * ed25519-sign each artifact, measured off-network. This is the
 * deterministic reference against which every remote mechanism's network
 * cost is compared.
 *
 * Usage: tsx src/local-primitive.ts [--reps 100]
 */

const CSV_PATH: string = join(RUNS_DIR, "local-primitive.csv");
const HEADER = "artifact_id;bytes;hash_ms_median;sign_ms_median;reps";

function median(values: readonly number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const a = sorted[mid];
  const b = sorted[sorted.length % 2 === 0 ? mid - 1 : mid];
  if (a === undefined || b === undefined) return Number.NaN;
  return (a + b) / 2;
}

function main(): void {
  const argv = process.argv.slice(2);
  const repsIndex = argv.indexOf("--reps");
  const reps = repsIndex >= 0 ? Number(argv[repsIndex + 1] ?? "100") : 100;
  const { privateKey } = generateKeyPairSync("ed25519");
  const artifacts = buildArtifacts();

  if (!existsSync(CSV_PATH)) {
    mkdirSync(dirname(CSV_PATH), { recursive: true });
    writeFileSync(CSV_PATH, `${HEADER}\n`, "utf8");
  }
  for (const artifact of artifacts) {
    const content = readFileSync(artifact.path);
    const hashTimes: number[] = [];
    const signTimes: number[] = [];
    for (let i = 0; i < reps; i += 1) {
      const t0 = nowMs();
      createHash("sha256").update(content).digest();
      const t1 = nowMs();
      sign(null, content, privateKey);
      const t2 = nowMs();
      hashTimes.push(t1 - t0);
      signTimes.push(t2 - t1);
    }
    appendFileSync(
      CSV_PATH,
      `${artifact.id};${content.length};${median(hashTimes).toFixed(4)};${median(signTimes).toFixed(4)};${reps}\n`,
      "utf8",
    );
    console.log(
      `${artifact.id.padEnd(12)} ${String(content.length).padStart(8)} B  hash ${median(hashTimes).toFixed(3)} ms  sign ${median(signTimes).toFixed(3)} ms`,
    );
  }
  console.log(`\nRows written to ${CSV_PATH}`);
}

main();
