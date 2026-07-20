# prov-anchor-bench

Benchmark of cryptographic provenance-anchoring mechanisms for machine-learning artifacts.

This repository compares, under a single experimental harness, four ways of anchoring the provenance chain of ML pipeline artifacts (datasets, transformations, configurations, models):

| Mechanism | Backend | Trust model |
|---|---|---|
| Soroban smart contract | Stellar testnet | Public network consensus |
| Stellar classic operation | Stellar testnet | Public network consensus |
| Rekor (hashedrekord) | Sigstore public transparency log | Single auditable operator |
| Local append-only log | Local filesystem (control) | None (baseline) |

Each artifact is described by a minimal W3C PROV-DM record; the anchor stores the SHA-256 of the artifact and of its provenance record, chained to the previous anchor, so that third parties can verify both the integrity of every link and the completeness of the chain.

## Status

**Exploratory pilot.** The pilot protocol is pre-registered in [`docs/protocolo-piloto.md`](docs/protocolo-piloto.md) (in Portuguese) before any measurement code or data was committed — the commit history documents the order. Pilot results will be reported in `docs/resultados-piloto.md`.

## Repository layout

```
contracts/anchor/   Minimal Soroban anchoring contract (Rust, soroban-sdk — contracts are Rust by platform requirement)
harness/            Measurement harness (Python 3.11+, stellar-sdk)
analysis/           Descriptive analysis of pilot runs (Python)
docs/               Pre-registered protocol and results
```

## Quickstart

```bash
# 1. Build and deploy the contract (requires Rust + stellar-cli, testnet account via friendbot)
cd contracts/anchor && stellar contract build

# 2. Install the harness dependencies (from the repository root)
pip install -r harness/requirements.txt

# 3. Run a smoke test (3 operations per mechanism)
python -m harness.run_pilot --smoke

# 4. Run a pilot window (balanced randomized order, CSV output)
python -m harness.run_pilot --window 1
python -m harness.baseline_probe --minutes 10   # in parallel, separate terminal

# 5. Verify the provenance chain and time the local primitive
python -m harness.verify_chain
python -m harness.local_primitive

# 6. Analyze
python analysis/pilot_analysis.py
```

Only public data is anchored (hashes of artifacts derived from public INMET/BDMEP weather series). Testnet keys are disposable. Rekor entries are public and permanent by design; nothing identifying is ever uploaded — hashes only.

## License

Apache-2.0. See [LICENSE](LICENSE).
