# Botkeep branch package — validation

## Provenance and scope

Prepared from the supplied `StudyRoute.zip`, not from an older project copy. The current web UI, ONNX NLU/explainer/risk artifacts, dialogue policy, cookie-session authentication, encrypted per-account provider-key storage, and current-question language selection were retained.

Added a single-process Python hosting entry point (`main.py`), root requirements indirection, same-origin prebuilt frontend hosting, an explicit public HTTPS origin for cookie/origin validation, committed frontend assets with integrity checks, GitHub workflows, and the Bangla deployment guide. The assistant's connection settings stay above the conversation. A flex sizing correction keeps the conversation scroll area contained.

Real `.env` files, private/generated secrets, runtime databases, `.git` history, dependency folders and caches are excluded. The release manifest is generated fresh for this archive. Do not upload the original unfiltered archive to a public repository.

## Completed locally

- Backend suite: **1,679 passed, 1 skipped**. Includes new hosting, CSP, origin validation, HTTPS secure-cookie, session restoration and restart checks.
- Frontend unit suite: **463 passed across 41 files**.
- Production frontend build, ESLint and TypeScript checks passed.
- Desktop/mobile Playwright smoke suite: **24 passed** (mocked backend).
- Additional browser integration against the actual Python API + SQLite: parent login, refresh, new-tab restore, top connection settings, local/offline chat, mobile student login, no horizontal overflow or JavaScript errors.
- Complete 14-stage simulated payment/demo flow against a fresh local Git checkout: **all demo checks passed**.
- The branch package was locally committed and cloned; committed frontend integrity verification and the existing repository scanner passed. NLU, explainer and risk model artifacts loaded after this Git checkout.
- The unchanged repository secret scanner passed for the prepared source. Committed frontend: **132 files**. ZIP entries and the generated SHA-256 manifest are independently checked during final handoff.

## Not claimed / deployment requirements

No files were pushed to GitHub, no GitHub workflow was run remotely, and no Botkeep workload was created. Botkeep's actual package installation, memory/disk headroom, persistent storage behavior, assigned port and HTTPS routing must be checked on the user's account. Local backend testing used Python 3.13; the managed-host recommendation is Python 3.12. Node 24 was used only for preparing the committed frontend.

Live Gemini/Groq/Hugging Face quota, latency and language compliance were not tested with private credentials. A provider label or local `ai_mode=llm` is not evidence of a successful remote provider call. Offline integration used the project's local features. Rate-limit errors cannot be removed by this package.

Saved provider keys require a persistent matching database and encryption key. Configure `PUBLIC_ORIGIN`, stable private encryption settings and persistent `DATA_DIR` before public use. The API-key input intentionally stays blank after a save; connection metadata identifies a saved key. Never store API keys in committed source or public frontend variables.

This remains a synthetic-data sandbox, not a real-money production deployment. The project audit demo also reports its existing limitation: rewriting both SQLite audit logs can pass after restart. Hosting changes do not turn that into an external tamper-proof ledger.

See `BOTKEEP_DEPLOY_BN.md` for GitHub branch creation, exact environment settings, deployment and update steps.
