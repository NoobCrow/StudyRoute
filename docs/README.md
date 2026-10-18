# Documents

Start with the technical documentation. Everything else is detail behind it. All of it describes a sandbox:
synthetic data, simulated banks, no real money.

## The submission documents

| Document | What it is |
|----------|------------|
| [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) | The mandatory report: architecture, core algorithms and trained components, security design, verification, limits. The PDF is in `submission/` |
| [SECURITY_SELF_ASSESSMENT.md](SECURITY_SELF_ASSESSMENT.md) | Permission tiers (checked against the code by a test) and the list of known risks |
| [BUSINESS_CASE.md](BUSINESS_CASE.md) | Who pays, who benefits, the sourced market figures and what would have to be true |
| [COMPETITION_RULES.md](COMPETITION_RULES.md) | The official rules, and how each requirement is met |
| [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | What is unverified or not done, and what only a person can supply |

## How it works

| Document | What it is |
|----------|------------|
| [BLUEPRINT.md](BLUEPRINT.md) | The specification the build follows (sections 1 to 16 and 22) |
| [SECURITY.md](SECURITY.md) | The threat matrix, with the test that proves each row |
| [AUDIT_TRUST_BOUNDARY.md](AUDIT_TRUST_BOUNDARY.md) | What the audit log proves and what it does not; the outside checkpoint |
| [BANK_NETWORK.md](BANK_NETWORK.md), [BANK_REVIEW.md](BANK_REVIEW.md), [SMART_ESCROW.md](SMART_ESCROW.md) | The simulated bank network, the bank's review desk, the escrow on a simulated chain |
| [DOCKER.md](DOCKER.md) | Running the stack with Docker |

## The trained components

| Document | What it is |
|----------|------------|
| [AI_AGENT.md](AI_AGENT.md), [AI_EVALUATION.md](AI_EVALUATION.md) | The reader that proposes intents and marks values, and its measurement against rules |
| [AI_RL.md](AI_RL.md), [AI_RL_EVALUATION.md](AI_RL_EVALUATION.md) | The dialogue policy (when to ask, read back or plan) and its evaluation |
| [AI_EXPLAINER.md](AI_EXPLAINER.md) | The small explainer that rewords the engine's answer, with every rewrite checked in code |
| [AI_RISK.md](AI_RISK.md), [AI_RISK_MODELS.md](AI_RISK_MODELS.md) | The risk router: what it learned, how 24 configurations compare, and its limits |

## Evidence and verification

| Document | What it is |
|----------|------------|
| [TEST_CASES.md](TEST_CASES.md) | Blueprint scenarios T01 to T24 and every test file |
| [SECURITY_TESTING.md](SECURITY_TESTING.md) | The attacks, tracking and data-leakage checks run against the live app |
| [CORRIDOR_VALIDATION.md](CORRIDOR_VALIDATION.md) | A source-checked look at one corridor, and what it does not prove |
| [PROVENANCE.md](PROVENANCE.md), [THIRD_PARTY.md](THIRD_PARTY.md) | Where the code and data came from, and the licences of what is used |
| [`../submission/evidence/`](../submission/evidence/README.md) | The recorded runs these documents cite |

Diagrams (Mermaid source and PNG) are in [diagrams/](diagrams/README.md).
