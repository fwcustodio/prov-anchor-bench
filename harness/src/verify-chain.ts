import { randomBytes } from "node:crypto";
import { buildArtifacts } from "./artifacts.js";
import { buildChain, verifyChain } from "./prov.js";

/**
 * Rebuilds the artifact chain and verifies it end to end; then demonstrates
 * that suppressing a link is detected (functional validation of the chain
 * construction).
 *
 * Usage: tsx src/verify-chain.ts
 */

function main(): void {
  const artifacts = buildArtifacts();
  const chain = buildChain(
    artifacts.map(({ id, sha256, stepType, usedIds }) => ({ id, sha256, stepType, usedIds })),
    "prov-anchor-bench-pilot",
    randomBytes(8).toString("hex"),
  );

  const intact = verifyChain(chain);
  console.log(`full chain (${chain.length} links): ${intact === -1 ? "VERIFIED" : `BROKEN at ${intact}`}`);

  const suppressed = [...chain.slice(0, 5), ...chain.slice(6)];
  const broken = verifyChain(suppressed);
  console.log(`chain with link 5 suppressed: ${broken === -1 ? "NOT DETECTED (error)" : `break detected at index ${broken}`}`);

  if (intact !== -1 || broken === -1) {
    process.exitCode = 1;
  }
}

main();
