#![no_std]
use soroban_sdk::{contract, contractimpl, symbol_short, BytesN, Env, Symbol};

const SEQ: Symbol = symbol_short!("seq");
const HEAD: Symbol = symbol_short!("head");

// TTL bounds for persistent entries, in ledgers (~5 s each).
// Entries are rent-based on Soroban: they expire unless extended, so the
// maintenance cost of long-lived anchors is an explicit dimension here.
const TTL_THRESHOLD: u32 = 100_000;
const TTL_EXTEND_TO: u32 = 200_000;

#[contract]
pub struct AnchorContract;

#[contractimpl]
impl AnchorContract {
    /// Anchor one artifact: records the new chain head and emits an event
    /// carrying the artifact hash, the hash of its provenance record and
    /// the previous head, so the full chain is reconstructable from the
    /// event stream. Returns the sequence number of this anchor.
    pub fn anchor(
        env: Env,
        artifact_hash: BytesN<32>,
        prov_hash: BytesN<32>,
        prev: BytesN<32>,
    ) -> u64 {
        let storage = env.storage().persistent();
        let seq: u64 = storage.get(&SEQ).unwrap_or(0) + 1;
        storage.set(&SEQ, &seq);
        storage.set(&HEAD, &artifact_hash);
        storage.extend_ttl(&SEQ, TTL_THRESHOLD, TTL_EXTEND_TO);
        storage.extend_ttl(&HEAD, TTL_THRESHOLD, TTL_EXTEND_TO);
        env.events()
            .publish((symbol_short!("anchor"), seq), (artifact_hash, prov_hash, prev));
        seq
    }

    /// Current head of the anchored chain, if any.
    pub fn head(env: Env) -> Option<BytesN<32>> {
        env.storage().persistent().get(&HEAD)
    }

    /// Number of anchors recorded so far.
    pub fn seq(env: Env) -> u64 {
        env.storage().persistent().get(&SEQ).unwrap_or(0)
    }
}

#[cfg(test)]
mod test {
    use super::*;
    use soroban_sdk::Env;

    #[test]
    fn anchors_and_updates_head() {
        let env = Env::default();
        let id = env.register(AnchorContract, ());
        let client = AnchorContractClient::new(&env, &id);

        let a1 = BytesN::from_array(&env, &[1u8; 32]);
        let p1 = BytesN::from_array(&env, &[2u8; 32]);
        let zero = BytesN::from_array(&env, &[0u8; 32]);

        assert_eq!(client.seq(), 0);
        assert_eq!(client.anchor(&a1, &p1, &zero), 1);
        assert_eq!(client.head(), Some(a1.clone()));

        let a2 = BytesN::from_array(&env, &[3u8; 32]);
        let p2 = BytesN::from_array(&env, &[4u8; 32]);
        assert_eq!(client.anchor(&a2, &p2, &a1), 2);
        assert_eq!(client.seq(), 2);
        assert_eq!(client.head(), Some(a2));
    }
}
