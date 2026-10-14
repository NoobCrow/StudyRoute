# Contracts

Solidity for the StudyRoute **sandbox chain**. Design and flows: [docs/SMART_ESCROW.md](../docs/SMART_ESCROW.md).

| Contract | What it is |
|----------|-----------|
| `src/TokenisedDeposit.sol` | A bank-issued tokenised deposit, one per currency (an ERC-20 subset). Only the issuer mints. |
| `src/TuitionEscrow.sol` | Locks a token for a beneficiary in up to 60 tranches. The compliance role can freeze, nothing more. |
| `src/AuditAnchor.sol` | Append-only list of audit-log head hashes. |

This folder is a **build tool only**. The backend runs the compiled artifacts that are committed in
`backend/app/chain/artifacts/`, so neither Node nor a compiler is needed to run the project.

```bash
cd contracts
npm ci
npm run build      # writes backend/app/chain/artifacts/*.json
```

* `solc` 0.8.37 from the `solc` npm package (WebAssembly, no download), `evmVersion: paris`,
  optimizer on (200 runs). `js-sha3` computes event topics for the artifacts.
* The build is deterministic. CI rebuilds and fails if the committed artifacts differ.
* Each artifact stores the SHA-256 of its source file; `backend/tests/test_chain_contracts.py` checks
  them, so a contract cannot change without being rebuilt.
* `package.json` overrides `tmp` to a patched release so that `npm audit` is clean.

Everything runs on a simulated, in-memory EVM. Nothing has been deployed to any real network, and
nothing here is money.
