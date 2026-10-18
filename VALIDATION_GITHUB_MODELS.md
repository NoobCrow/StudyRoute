# GitHub + GitHub Release deployment validation

Prepared from the user's supplied `StudyRoute-botkeep.zip`. This edition is not cloud-only. Original reader/explainer weights, tokenizer files, dialogue/risk artifacts, training source/data and submission/media were compared byte-for-byte after restoration. Runtime app code, UI and application features remain; `main.py` adds a pinned Release bootstrap and a required-model startup check.

## Verified locally
- Bootstrap suite: **15 tests passed**. Covers archive/file hashes, traversal/symlink/unexpected-entry rejection, cache restore, download failures, mocked private API redirect with token stripped before the asset CDN, and required-model startup failure.
- Existing hosting/browser-session/cloud-adapter/response-language regression subset: **99 passed**.
- The supplied frontend's integrity manifest: **132 public files verified**. No frontend rebuild or UI redesign was performed in this edition.
- Original repository scanner passed without weakening its rules.
- Actual original ONNX reader, ONNX explainer, dialogue policy and risk scorer loaded after restoring the real Release asset from a local persistent cache. The real hosted app returned successful UI and API health responses with the local explainer selected.
- The source + Release asset union preserves original model weights, dialogue/risk artifacts, training source/data and submission/media byte-for-byte. They were relocated, not replaced with templates or cloud models.
- Import limits checker conservatively requires at most 950 files, under 3.8 MB per file, and at most 18 MB total raw source. These are below the limits shown in the user's Botkeep panel (1,000 files, 4 MB/file, 20 MB total). SHA-256 manifests are verified in the final archives.

## Not yet verified on remote services
No repository push, GitHub Release publish, private live GitHub asset download, Botkeep installation, public HTTPS routing or remote startup has been performed. The real download path was simulated using an HTTPS client mock; actual model bytes were restored from a local cache and loaded locally. Real provider API calls were not tested. The full historical backend/frontend test suites were not rerun for this packaging change; only the listed regression subset and bootstrap suite were run.

Botkeep must permit outbound GitHub API/Release-CDN access and enough first-boot time for the download. Complete pinned runtime dependencies, including ONNX Runtime and sentencepiece, must be installed before main.py runs. A missing required reader/dialogue/risk model, or local explainer when local mode is selected, fails startup rather than silently hiding the missing model.

Private repository Release assets require a separate read-only server token. Stable database/encryption settings and a persistent writable DATA_DIR are still required. Smaller Git-import size does not reduce the runtime's original CPU/RAM/dependency storage requirements; the user's 2 GB Botkeep allocation has not been capacity-tested remotely.
