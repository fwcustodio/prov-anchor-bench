import { closeSync, fsyncSync, openSync, writeSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { RUNS_DIR } from "./config.js";
import type { ChainedArtifact } from "./prov.js";
import { nowMs } from "./measure.js";

export interface ControlResult {
  readonly latencyMs: number;
  readonly offset: number;
}

/**
 * Control mechanism: appends the anchor to a local append-only log and
 * fsyncs, so the measured latency includes durable local persistence —
 * the baseline every remote mechanism is compared against.
 */
export class ControlAnchor {
  private readonly logPath: string;
  private offset = 0;

  constructor(runLabel: string) {
    this.logPath = join(RUNS_DIR, `control-log-${runLabel}.jsonl`);
    mkdirSync(dirname(this.logPath), { recursive: true });
  }

  anchor(link: ChainedArtifact): ControlResult {
    const line = `${JSON.stringify({
      artifact: link.artifactSha256,
      record: link.recordSha256,
      prev: link.prevArtifactSha256,
    })}\n`;
    const t0 = nowMs();
    const fd = openSync(this.logPath, "a");
    try {
      writeSync(fd, line);
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
    const t1 = nowMs();
    this.offset += line.length;
    return { latencyMs: t1 - t0, offset: this.offset };
  }
}
