# Submission checklist

Source: the official rules, "PBCSF Appendix 2: Problem Description and Competition Rules for
International Track" (read on 14 Oct 2026; a public copy is on the ITS Indonesia site), and the
CMU Thailand announcement. Check the official site once more for changes:
https://fintechathon.g-ican.com/#/en

**Deadline: 20 Oct 2026, 23:59 Beijing time = 21:59 in Dhaka (15:59 UTC).** Registration and
submission share it. **Internal target: the evening of Monday 19 Oct, Dhaka time.** Submissions may
be updated any time before the deadline and the latest version received counts; nothing is accepted
after it. Keep a copy of every e-mail you send and any reply.

## 0. Can you enter? (rules, "Eligibility and Teaming")

- [ ] **A team has 2 to 5 students.** A one-person entry is not allowed: find at least one
      teammate before registering.
- [ ] Every member is a full-time student (undergraduate, master's or PhD) at a university or
      research institution **outside** Mainland China, Hong Kong SAR, Macao SAR and Chinese Taipei.
- [ ] **At least 60% of the team are non-Chinese nationals.** In practice: 2 members need 2
      non-Chinese, 3 need 2, 4 need 3, 5 need 3. The organiser assigns the track from
      nationalities and institutions.
- [ ] Nobody is in two teams (Domestic and International tracks count together; a duplicate
      registration is invalid).
- [ ] The work is the team's own. Third-party code and open-source parts are licensed (see
      `docs/THIRD_PARTY.md`).
- [ ] At least one member can **attend the final in person** if invited (Shenzhen, 20 to 23 Nov).
      A finalist team that is absent without valid justification loses its awards.

## 1. Register (do this first; the deadline is the same)

- [ ] Download the registration form (link in the CMU announcement).
- [ ] Fill it in. Attach **each member's passport bio page**. Never put these in the repository,
      the archive or any chat.
- [ ] E-mail the form and passport pages to **wangyr@pbcsf.tsinghua.edu.cn** (draft in
      `EMAIL_TEMPLATES.md`). Use the subject format printed on the form.
- [ ] Keep the confirmation. Registration is free: anyone asking for money is not the organiser.

## 2. The six deliverables (official list)

| # | Deliverable | Required | Where it is in this repository | Still yours |
|---|-------------|----------|--------------------------------|-------------|
| 01 | **Technical documentation**: system architecture, core algorithm description, security design | Yes | `docs/TECHNICAL_DOCUMENTATION.md` (links `docs/SECURITY.md`) | Export to PDF if you want one file |
| 02 | **Presentation deck**, final presentation no longer than 10 minutes | Yes | **`submission/StudyRoute_Deck.pptx`** (11 slides with speaker notes, under a minute each); source `submission/deck/build_deck.js`; outline in `submission/DECK_OUTLINE.md` | Replace `[Team name]` and `[repository link]` on slides 1 and 11, then rehearse to 10 minutes |
| 03 | **Demo video**, no longer than 5 minutes | Optional, but see 06 | Shot-by-shot script in `submission/VIDEO_SCRIPT.md` | Record it |
| 04 | **Source code** with README, GitHub repository link, deployment instructions and test cases | Yes | `README.md` (setup and deployment), `docs/TEST_CASES.md` (T01 to T24 and every test file), `backend/`, `frontend/`, `docker-compose.yml` | **Create the GitHub repository and push** (see below); add its link to the e-mail |
| 05 | **Security self-assessment report**: permission-tier implementation and known-risk list | Yes | `docs/SECURITY_SELF_ASSESSMENT.md` | Read the risk list and agree with it |
| 06 | **Execution evidence**: for non-on-chain topics, simulated-account or sandbox operation logs **and** demo video | Yes | `submission/evidence/` (operation log, full audit log, Verify result, payments with UETR, tamper demo) | The demo video (see 03) |

Scoring (all topics): **task completion 40%, security and compliance 30%, innovation and
interaction 30%**. Topic C is described as real financial pain points of international students and
cross-border users, such as remittances, tuition payments, credit building and multi-currency
management. StudyRoute covers remittance and tuition end to end; credit building and
multi-currency management are listed as next steps, not built.

### Putting the code on GitHub (deliverable 04)

```bash
git remote add origin https://github.com/<you>/<repo>.git     # create the empty repository first
git push -u origin main
```

Run `python scripts/scan_repo.py` first (it must be clean). Make the repository public or give the
judges access; put the link in the submission e-mail.

## 3. Technical gate (all must pass before you send)

- [x] From a clean clone on a machine with Docker: `docker compose up --build`, open
      http://localhost:8080, sign in with a demo account. Done on 15 Oct 2026 from the unzipped
      archive in a Linux VM (Docker 29.1.3, Compose 2.40.3); details in `docs/DOCKER.md`. Repeat it
      on your own machine if you can (Docker Desktop on Windows was not tried).
- [x] `python scripts/docker_smoke.py` prints "All smoke checks passed." against the running stack
      (also with `docker-compose.hardened.yml`).
- [x] `docker compose exec backend python -m app.scripts.demo_flow` prints "All demo checks passed."
- [ ] `cd backend && pytest -q && ruff check . && ruff format --check .`
- [ ] `cd frontend && npm run typecheck && npm test && npm run build`
- [ ] CI is green on the pushed commit (backend, frontend, secret scan, dependency audit, docker).
- [ ] `python scripts/scan_repo.py` is clean (secrets, real e-mails, passport-like numbers, TODOs).
- [ ] Every screen shows the sandbox banner (sign-in page included).
- [ ] If you will show model mode: set `LLM_PROVIDER`, `LLM_API_KEY` and a pinned `LLM_MODEL` in
      `.env`, run `python -m app.scripts.check_ai` (must print OK), restart, and confirm the
      "Model: ..." badge in the chat. Otherwise say "template mode".
- [ ] Regenerate the evidence if the code changed: `python -m app.scripts.export_evidence --tamper`
      (needs a running API with fresh demo data).
- [ ] Fill in the placeholders in `PROJECT_DESCRIPTION.md` and `DECK_OUTLINE.md` (team name,
      members, contact).
- [ ] Freeze the code. Commit. Tag the commit you submit.

## 4. Build and send

- [ ] `python scripts/personalize.py --team "..." --repo "https://github.com/..."` fills the team name
      and repository link into the documents and the deck (add `--members "A (University), B (University)"`).
- [ ] `python scripts/preflight.py` prints OK, FAIL and OPEN lines. Fix every FAIL; every OPEN line
      is something only a person can do (team, registration, GitHub, Docker, video, the e-mail).
- [ ] `python scripts/make_submission.py` writes `dist/studyroute-submission.zip` (refuses to build
      if the scan finds a problem). Unzip it elsewhere and run it once.
- [ ] Send **one e-mail, in English**, to wangyr@pbcsf.tsinghua.edu.cn with the six items above:
      the documentation, the deck, the video link or file, the GitHub link plus the archive, the
      self-assessment and the evidence (draft in `EMAIL_TEMPLATES.md`). Check the attachment size
      limit; link large files instead.
- [ ] Keep the sent e-mail and a backup copy of everything sent. An organiser reminder arrives 24
      hours before the deadline: do not wait for it.

## 5. Questions the rules answered (blueprint section 18)

| # | Item | Status |
|---|------|--------|
| 1 | Deadline | **Confirmed**: 20 Oct 2026, 23:59 Beijing (21:59 Dhaka) |
| 2 | Submission format and deliverables | **Confirmed**: the six items in section 2 |
| 3 | Scoring rubric | **Confirmed**: 40% task completion, 30% security and compliance, 30% innovation and interaction |
| 4 | Mandatory API, dataset or test environment | **None stated.** The rules ask for sandbox operation logs, so our own sandbox API is what is submitted |
| 5 | Topic C requirements | **Confirmed**: the description above, same scoring as every topic |
| 6 | Eligibility | **Confirmed**: section 0. Who qualifies is for you to check |
| 7 to 12 | Bangladesh Bank figures, circulars, ISO purpose code, university instructions | **Still open.** They stay `verified: false` in the app; see `docs/OPEN_QUESTIONS.md` |
