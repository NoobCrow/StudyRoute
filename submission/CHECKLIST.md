# Submission checklist

Repair-release status: see `evidence/release/VERIFICATION.md`. Historical Docker/Windows runs below are not fresh validation of this repaired tree. Confirm registration, team provenance, judge access and credential revocation yourself.

Source: the official rules, "PBCSF Appendix 2: Problem Description and Competition Rules for
International Track" (the full PDF is reproduced, with our check against it, in
`docs/COMPETITION_RULES.md`), and the CMU Thailand announcement. Check the official site once more for changes:
https://fintechathon.g-ican.com/#/en

**Deadline: 20 Oct 2026, 23:59 Beijing time = 21:59 in Dhaka (15:59 UTC).** Registration and
submission share it. **Internal target: the evening of Monday 19 Oct, Dhaka time.** Submissions may
be updated any time before the deadline and the latest version received counts; nothing is accepted
after it. Keep a copy of every e-mail you send and any reply.

## 0. Can you enter? (rules, "Eligibility and Teaming")

- [x] **A team has 2 to 5 students.** A one-person entry is not allowed. The team reported on
      17 Oct 2026 that it has registered as a team.
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
      A finalist team that is absent without valid justification loses its awards. Finalists are
      announced on 31 Oct and check in on 20 Nov, so find out the Chinese visa lead time for that
      member now.
- [ ] Only if the registration reply left it unclear: confirm how the 60% is counted, and whether
      your universities' country is eligible (one secondary page mentions "21 APEC economies"; the
      official PDF does not). Draft 1b in `EMAIL_TEMPLATES.md`; keep the reply.
- [ ] You can say, in your own words, who built which part and which tools you used (including any
      AI coding assistant), and you can explain every module. The rules require independent work.
      `QA_PREP.md` question 10 is where to write it down.

## 1. Register (do this first; the deadline is the same)

The team **registered by e-mail on 15 Oct 2026 at 21:25** as TeamEkxin (leader Farhan Labib; members
Md Redwan Hossen, Alim Bin Yeasin and Kalvin Chakma; Ahsanullah University of Science and Technology,
Bangladesh). The message is recorded in `REGISTRATION.md`. The three steps below are therefore ticked;
nothing in this repository can confirm what the organisers received.

- [x] Download the registration form (link in the CMU announcement).
- [x] Fill it in. Attach **each member's passport bio page**. Never put these in the repository,
      the archive or any chat.
- [x] E-mail the form and passport pages to **wangyr@pbcsf.tsinghua.edu.cn** (draft in
      `EMAIL_TEMPLATES.md`). Use the subject format printed on the form.
- [ ] **The organiser's confirmation has not been seen** (none was in the thread supplied on 17 Oct).
      If nothing has arrived by the evening of 18 Oct, write again. Keep every reply, and check that
      it did not raise a problem with the team's nationality mix or universities. Registration is free: anyone asking for
      money is not the organiser.

## 2. The six deliverables (official list)

The organiser's e-mail of 15 October 2026 says **items 01 and 02 are mandatory and items 03 to 06 are optional**,
and asks teams to submit as soon as possible (deadline unchanged: 20 October, Beijing time). Send all six anyway:
the optional ones are the evidence behind the scores.

| # | Deliverable | Required | Where it is in this repository | Still yours |
|---|-------------|----------|--------------------------------|-------------|
| 01 | **Technical documentation**: system architecture, core algorithm description, security design | **Yes (mandatory)** | **`submission/StudyRoute_Technical_Documentation.pdf`** (12 pages, one file, made from `docs/TECHNICAL_DOCUMENTATION.md`) | Open it once and read it; attach it |
| 02 | **Presentation deck**, final presentation no longer than 10 minutes | **Yes (mandatory)** | **`submission/StudyRoute_Deck.pptx`** (12 slides with speaker notes, under a minute each); source `submission/deck/build_deck.js`; outline in `submission/DECK_OUTLINE.md` | Confirm the retained original team attribution and private-fork link; rehearse to 10 minutes |
| 03 | **Demo video**, no longer than 5 minutes | Optional (the evidence item asks for it) | `submission/StudyRoute_Demo.mp4` and captions (actual repaired local UI/API, about 95 seconds); script in `submission/VIDEO_SCRIPT.md` | Watch it; add narration or a longer financial workflow if useful |
| 04 | **Source code** with README, GitHub repository link, deployment instructions and test cases | Optional | `README.md` (setup and deployment), `docs/TEST_CASES.md` (T01 to T24 and every test file), `backend/`, `web/`, `docker-compose.yml` | **Safely update the existing fork** using `GITHUB_PUSH_BN.md`; add the accessible link to the e-mail |
| 05 | **Security self-assessment report**: permission-tier implementation and known-risk list | Optional | `docs/SECURITY_SELF_ASSESSMENT.md`; one-file version **`submission/StudyRoute_Security_Self_Assessment.pdf`** (11 landscape pages) | Read the risk list and agree with it |
| 06 | **Execution evidence**: for non-on-chain topics, simulated-account or sandbox operation logs **and** demo video | Optional | `submission/evidence/` (operation log, full audit log, Verify result, payments with UETR, tamper demo) | Watch the included demo (03); verify the evidence scope |

Scoring (all topics): **task completion 40%, security and compliance 30%, innovation and
interaction 30%**. Topic C is described as real financial pain points of international students and
cross-border users, such as remittances, tuition payments, credit building and multi-currency
management. StudyRoute covers remittance and tuition end to end; credit building and
multi-currency management are listed as next steps, not built.

### Putting the code on GitHub (deliverable 04)

Use `GITHUB_PUSH_BN.md` for the existing `redwan786/StudyRoute` fork. Do not add another
remote blindly or overwrite teammates' uncommitted work. Revoke exposed credentials first,
scan before committing and give judges access to a private repository. Do not force-push.

## 3. Technical gate (all must pass before you send)

- [ ] Re-test this repair from a clean clone on a machine with Docker: `docker compose up --build`, open
      http://localhost:8080, sign in with a demo account. Inherited evidence reports runs on 15 and 17 Oct 2026 from the unzipped
      archive in a Linux VM (Docker 29.1.3, Compose 2.40.3); details in `docs/DOCKER.md`. Repeat it
      on your own machine if you can (Docker Desktop on Windows was not tried).
- [ ] Re-run `python scripts/docker_smoke.py` prints "All smoke checks passed." against the running stack
      (also with `docker-compose.hardened.yml`).
- [ ] Re-run `docker compose exec backend python -m app.scripts.demo_flow` prints "All demo checks passed."
- [x] `cd backend && pytest -q && ruff check . && ruff format --check .` (current repair: use the exact local results in `evidence/release/VERIFICATION.md`; not a new Windows/container claim)
- [x] `cd web && npm run typecheck && npm run lint && npm test && npm run build && npm run e2e` (current repair: 439 Vitest tests and 24 desktop/mobile production-CSP browser tests; browser API fixtures are mocked, while the recorded demo uses the actual local API)
- [ ] CI is green on the pushed commit (backend, web, contracts, secret scan, dependency audit, docker).
- [x] `python scripts/scan_repo.py` is clean (secrets, real e-mails, passport-like numbers, TODOs). Clean on 17 Oct 2026.
- [ ] Every screen shows the sandbox banner (sign-in page included).
- [ ] If you will show model mode: set `LLM_PROVIDER`, `LLM_API_KEY` and a pinned `LLM_MODEL` in
      `.env`, run `python -m app.scripts.check_ai` (must print OK), restart, and confirm the
      "Model: ..." badge in the chat. Otherwise say "template mode".
- [x] Regenerate the evidence if the code changed: `python -m app.scripts.export_evidence --tamper` (done 17 Oct 2026 against the final code)
      (needs a running API with fresh demo data).
- [ ] Confirm the retained team name, members, contact, registration and ownership in `PROJECT_DESCRIPTION.md`, `REGISTRATION.md` and `DECK_OUTLINE.md`; a private fork does not transfer authorship.
- [ ] **Make the GitHub repository public** (Settings, then Danger Zone, then Change visibility) before submitting, and open the link in a private browser window to check it loads without signing in. The team will do this.
- [ ] **Record the voiced pitch video** (5 minutes at most) from `submission/VIDEO_SCRIPT.md`, including the AI risk score and bank review scene. The team will do this. The interim `StudyRoute_Demo.mp4` has no voiceover.
- [ ] Send the organiser the eligibility question (draft 1b in `submission/EMAIL_TEMPLATES.md`) and keep their reply: an IEEE page describes the track as limited to 21 APEC economies, which the official PDF does not say.
- [ ] Freeze the code. Commit. Tag the commit you submit.

## 4. Build and send

- [ ] Review attribution and repository link in the included deck. Do not run personalization with invented team details.
- [ ] `python scripts/preflight.py` prints OK, FAIL and OPEN lines. Fix every FAIL; every OPEN line
      is something only a person can do (team, registration, GitHub, Docker, video, the e-mail).
- [ ] `python scripts/make_submission.py` writes `dist/studyroute-submission.zip` (refuses to build
      if the scan finds a problem). Unzip it elsewhere and run it once.
- [ ] Send **one e-mail, in English**, to wangyr@pbcsf.tsinghua.edu.cn with the six items above:
      the documentation, the deck, the video link or file, the GitHub link plus the archive, the
      self-assessment and the evidence (draft in `EMAIL_TEMPLATES.md`). Check the attachment size
      limit; link large files instead.
- [ ] Read `submission/QA_PREP.md` out loud once with the whole team. The online review and the
      final both ask these questions, and several answers are yours to write.
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
