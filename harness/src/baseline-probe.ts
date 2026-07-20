import { appendFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { rpc } from "@stellar/stellar-sdk";
import { REKOR_URL, RPC_URL, RUNS_DIR } from "./config.js";
import { nowMs, sleep } from "./measure.js";

/**
 * Baseline load probe: once per minute, measures the round-trip time of a
 * trivial request against each remote instance (Stellar RPC latest ledger;
 * Rekor log info). Run in parallel with measurement windows; the output is
 * the per-window baseline covariate.
 *
 * Usage: tsx src/baseline-probe.ts [--minutes 90]
 */

const CSV_PATH: string = join(RUNS_DIR, "baseline-probe.csv");
const HEADER = "at_iso;instance;rtt_ms;ok";

function appendProbe(instance: string, rttMs: number, ok: boolean): void {
  if (!existsSync(CSV_PATH)) {
    mkdirSync(dirname(CSV_PATH), { recursive: true });
    writeFileSync(CSV_PATH, `${HEADER}\n`, "utf8");
  }
  appendFileSync(CSV_PATH, `${new Date().toISOString()};${instance};${rttMs.toFixed(1)};${ok ? 1 : 0}\n`, "utf8");
}

async function probeStellar(server: rpc.Server): Promise<void> {
  const t0 = nowMs();
  try {
    await server.getLatestLedger();
    appendProbe("stellar-rpc", nowMs() - t0, true);
  } catch {
    appendProbe("stellar-rpc", nowMs() - t0, false);
  }
}

async function probeRekor(): Promise<void> {
  const t0 = nowMs();
  try {
    const response = await fetch(`${REKOR_URL}/api/v1/log`, { headers: { Accept: "application/json" } });
    appendProbe("rekor", nowMs() - t0, response.ok);
  } catch {
    appendProbe("rekor", nowMs() - t0, false);
  }
}

async function main(): Promise<void> {
  const argv = process.argv.slice(2);
  const minutesIndex = argv.indexOf("--minutes");
  const minutes = minutesIndex >= 0 ? Number(argv[minutesIndex + 1] ?? "90") : 90;
  const server = new rpc.Server(RPC_URL);
  const rounds = Math.max(1, Math.floor(minutes));
  console.log(`probing every 60 s for ${rounds} minutes -> ${CSV_PATH}`);
  for (let i = 0; i < rounds; i += 1) {
    await Promise.all([probeStellar(server), probeRekor()]);
    if (i < rounds - 1) await sleep(60_000);
  }
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
