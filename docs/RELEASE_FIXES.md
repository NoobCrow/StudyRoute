# Reviewed repair release — 17 October 2026

## Implemented
1. JSON is no longer globally exempt from credential scanning; Hugging Face tokens, quoted JSON
   signing/encryption secrets and private-key blocks are checked. Private environment/key-store files
   cause refusal. Deliberate synthetic test keys have narrowly documented fixture exemptions.
2. No-Git source traversal prunes dependencies/builds instead of recursively walking them. It keeps
   `ml/data` benchmark inputs, excludes runtime data and symlinks, and works after a Next.js build.
   Archive filtering is independent defence in depth, not permission to keep exposed secrets.
3. The default trained-dialogue API has an explicit deterministic review envelope: clarify missing or
   conflicting slots, ask for a missing date (or explicit “no deadline”), then read values back before
   building a plan. A turn limit cannot skip that review. Payment creation/approval remains human-only.
4. Local audit anchors are correctly described in UI, source, docs and deck. A database-owner rewrite
   of both audit and replay logs is reproduced in a limitation regression. A separately protected
   external-checkpoint CLI detects rewriting of a trusted prefix even after both logs are rehashed.
5. AI evaluations record model/data/source hashes, software versions and scope. The frozen blind set is
   labelled as reused, not a new study; raw RL simulator results are separate from runtime API review.
6. Fee wording no longer implies OUR guarantees full beneficiary receipt. The compare UI warns that
   accepted institutional routes matter. Official MMU guidance is a documented counterexample;
   the real corridor dossier is explicitly partial, not a bank quote or a usable live integration.
7. Fresh synthetic execution evidence, repaired-UI demo recording, regression results and archive
   inventory are provided with reproducible commands and limitations.

## Limits that cannot honestly be fixed by editing a ZIP
- Previously exposed credentials must be revoked/rotated in the relevant accounts by their owner.
  This release does not modify deployed servers or discard encrypted data.
- No live binding quote, regulated bank integration, real student usability study, external penetration
  test or independent fresh blind NLU evaluation has been obtained.
- The checkpoint requires operationally independent storage; local EVM anchoring alone is not secure
  against a database owner. The command does not provision immutable infrastructure.
- `DIALOGUE_MODE=off` remains a documented legacy path without the trained-mode read-back envelope.
  The conversation state is a UX aid, not a substitute for server-enforced MFA, RBAC or approval hashes.
- Institution-specific route enforcement is not implemented; all provider comparisons remain synthetic.
- Cloud paths use existing mock coverage, not newly verified real-provider calls. Docker was unavailable
  in this environment; local Python/Next.js validation is not a fresh Docker certification.
- Team identity, source ownership/originality and judge access require human confirmation.

## Score integrity
These changes address known weaknesses but **do not certify 85+/100**. A competition score depends on
official judging, financial validation, demonstrable differentiation and evidence quality. Do not convert
passing unit tests or a polished UI into claims of real-world safety or guaranteed award potential.

See `submission/evidence/release/VERIFICATION.md` for exact observed results, not inherited counts.
