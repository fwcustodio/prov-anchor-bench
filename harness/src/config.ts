import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

export const HARNESS_ROOT: string = join(dirname(fileURLToPath(import.meta.url)), "..");

export const RPC_URL = "https://soroban-testnet.stellar.org";
export const HORIZON_URL = "https://horizon-testnet.stellar.org";
export const FRIENDBOT_URL = "https://friendbot.stellar.org";
export const REKOR_URL = "https://rekor.sigstore.dev";
export const NETWORK_PASSPHRASE = "Test SDF Network ; September 2015";

export const ARTIFACTS_DIR: string = join(HARNESS_ROOT, "artifacts");
export const RUNS_DIR: string = join(HARNESS_ROOT, "..", "analysis", "results");
export const DATA_DIR: string = join(HARNESS_ROOT, "data");

/** Local, git-ignored file holding disposable testnet secrets and the contract id. */
const SECRETS_PATH: string = join(HARNESS_ROOT, ".pilot-secrets.json");

export interface PilotSecrets {
  /** Secret seed of the disposable testnet account used for Soroban invocations. */
  readonly sorobanSecret: string;
  /** Secret seed of the disposable testnet account used for classic manageData operations. */
  readonly classicSecret: string;
  /** Deployed anchor contract id (C...). */
  readonly contractId: string;
}

function isPilotSecrets(value: unknown): value is PilotSecrets {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record["sorobanSecret"] === "string" &&
    typeof record["classicSecret"] === "string" &&
    typeof record["contractId"] === "string"
  );
}

export function loadSecrets(): PilotSecrets {
  if (!existsSync(SECRETS_PATH)) {
    throw new Error(
      `Missing ${SECRETS_PATH}. Create it with {"sorobanSecret":"S...","classicSecret":"S...","contractId":"C..."} (disposable testnet keys only).`,
    );
  }
  const parsed: unknown = JSON.parse(readFileSync(SECRETS_PATH, "utf8"));
  if (!isPilotSecrets(parsed)) {
    throw new Error(`${SECRETS_PATH} does not match the expected shape.`);
  }
  return parsed;
}

/** Mechanisms under comparison. */
export type Mechanism = "soroban" | "classic" | "rekor" | "control";
export const MECHANISMS: readonly Mechanism[] = ["soroban", "classic", "rekor", "control"];
