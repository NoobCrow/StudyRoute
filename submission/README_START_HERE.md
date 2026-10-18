# StudyRoute: start here

Team TeamEkxin, FinTechathon 2026, International Track, Topic C (Cross-border and Student Finance Assistant).
StudyRoute is a **sandbox**: every rate, fee, bank, KYC check and settlement is simulated, all data is synthetic,
and no real money moves. Its guidance is indicative only: confirm with your AD bank.

## The deliverables

The organiser's e-mail of 15 October 2026 makes items 1 and 2 mandatory and the rest optional.

| # | Deliverable | Open this | Source or detail |
|---|-------------|-----------|------------------|
| 1 | Technical documentation: system architecture, core algorithms, security design (mandatory) | [StudyRoute_Technical_Documentation.pdf](StudyRoute_Technical_Documentation.pdf) (20 pages) | [docs/TECHNICAL_DOCUMENTATION.md](../docs/TECHNICAL_DOCUMENTATION.md) |
| 2 | Presentation deck, 10 minutes (mandatory) | [StudyRoute_Deck.pptx](StudyRoute_Deck.pptx) (21 slides, speaker notes inside, about 8.7 minutes) | [deck/build_deck.js](deck/build_deck.js), [DECK_OUTLINE.md](DECK_OUTLINE.md) |
| 3 | Demo video, under 5 minutes (optional) | Script: [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md). The final narrated video is not included. A supporting silent screen recording is [StudyRoute_Demo.mp4](StudyRoute_Demo.mp4) | |
| 4 | Source code, README, deployment, test cases (optional) | [README.md](../README.md), then `docker compose up --build` and http://localhost:8080 | [docs/DOCKER.md](../docs/DOCKER.md), [docs/TEST_CASES.md](../docs/TEST_CASES.md) |
| 5 | Security self-assessment: permission tiers and known risks (optional) | [StudyRoute_Security_Self_Assessment.pdf](StudyRoute_Security_Self_Assessment.pdf) (39 pages; edition 1.2, including attack/leakage/MITM evidence and all 314 recorded check labels) | [Expanded report Markdown](StudyRoute_Security_Self_Assessment.md); [original control assessment](../docs/SECURITY_SELF_ASSESSMENT.md) |
| 6 | Execution evidence: operation logs, audit log and verification, tamper and restore (optional) | [StudyRoute_Execution_Evidence_Report.pdf](StudyRoute_Execution_Evidence_Report.pdf) (14 pages) | [evidence/README.md](evidence/README.md) indexes the raw files |

## How the claims were checked

* Every figure in the technical documentation is recomputed from the evidence files by
  `python submission/tools/verify_report_numbers.py` (65 of 65 agree, 18 October 2026).
* The tests that read the documents run with the rest: `cd backend && pytest -q`.
* `python scripts/preflight.py` checks the deliverables, the placeholders, the evidence and the deck's notes
  against the 10-minute limit; `python scripts/scan_repo.py` scans for secrets, real e-mails and TODOs.
* The raw output of the attack probes, the Docker run and the real-browser audit of 18 October 2026 is in
  [evidence/](evidence/README.md), each file with a SHA-256 in [evidence/SHA256SUMS.txt](evidence/SHA256SUMS.txt).
  The whole tree is covered by [RELEASE_MANIFEST.sha256](../RELEASE_MANIFEST.sha256).

## Check it

```bash
cd backend && pytest -q
# 1,679 backend tests on a machine that has the explainer fixture (1,678 pass, 1 skipped); a fresh clone collects 1,673, runs 1,672 and skips one module whose fixture is excluded by .gitignore. 463 web tests (439 in an earlier pre-merge log) and 24 browser tests.
# Fixture details: technical documentation, section 5.
```

**Real vs synthetic.** Real: the problem framing and the Bangladesh Bank volume figure (USD 881.7m, via The Observer). Synthetic: every rate, fee, provider, KYC result, bank and settlement. Simulated: the chain, the escrow and the bank network. The USD 8.8m figure is our arithmetic. Confirm every financial rule with your AD bank.

## Where things are

| Folder | What |
|--------|------|
| `backend/`, `web/`, `config/`, `contracts/` | The application: engine, domain, API, trained models, the interface, rules, the escrow contract |
| `ml/`, `scripts/` | Training and evaluation of the four trained components; the checks and probes |
| `docs/` | The documents, indexed in [docs/README.md](../docs/README.md) |
| `submission/` | This folder: the deliverables above, the deck builder, the screenshots, `tools/` (build and check the documents) |
| `submission/evidence/` | The recorded logs, probes, Docker run and evaluations |

## For the team

Rebuild the documents from their sources; do not edit a PDF.

```bash
# Technical documentation: edit docs/TECHNICAL_DOCUMENTATION.md, then build the PDF (needs Google Chrome)
pip install markdown pypdf
python submission/tools/build_report_pdf.py         # writes submission/StudyRoute_Technical_Documentation.pdf
python submission/tools/md_to_docx.py               # an editable Word copy (pip install python-docx)
python submission/tools/verify_report_numbers.py    # re-check every figure against the evidence files

# Deck: always with the team values, or "[Team name]" comes back (python scripts/preflight.py flags it)
cd submission/deck
TEAM_NAME="TeamEkxin" REPO_LINK="https://github.com/NoobCrow/StudyRoute" node build_deck.js
```

The e-mail text is in [EMAIL_TEMPLATES.md](EMAIL_TEMPLATES.md), section 2; the step-by-step list is
[CHECKLIST.md](CHECKLIST.md).
