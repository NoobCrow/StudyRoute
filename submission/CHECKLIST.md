# Submission checklist

Deadline: **20 Oct 2026, 23:59 Beijing time (21:59 Dhaka).** Internal target: the evening of
**Monday 19 Oct, Dhaka time.** Do not plan to submit in the last hour. Keep a copy of the sent
e-mail, its attachments and any reply.

## Only you can do these

- [ ] Download the official rules PDF and read it fully. Write the scoring rubric and exact
      deliverables into blueprint section 18 and into `docs/OPEN_QUESTIONS.md` (section A).
- [ ] Confirm every member meets the eligibility rules (at least 60% non-Chinese nationals,
      full-time overseas enrolment, one team per person across tracks).
- [ ] Complete the registration form and collect a passport bio page from every member.
      **Never put these in the repository or the archive.**
- [ ] Confirm the submission e-mail address and subject format on the official site before
      sending anything (the blueprint copy comes from other universities' announcements).
- [ ] Fill in the placeholders in `PROJECT_DESCRIPTION.md` and `DECK_OUTLINE.md` (team name,
      members, contact).
- [ ] Build the deck from `DECK_OUTLINE.md` (screenshots are in `submission/screenshots/`).
- [ ] Record the demo video (3 to 5 minutes, English, script in blueprint 19.1). Whether it is
      required is open (blueprint 1.6); record it anyway.
- [ ] Dry run with someone outside the team.

## Technical gate (all must pass before you build the archive)

- [ ] From a clean clone on a machine with Docker: `docker compose up --build`, open
      http://localhost:8080, sign in with a demo account. (Docker was not available where the
      project was built, so this one check is yours.)
- [ ] `docker compose exec backend python -m app.scripts.demo_flow` prints "All demo checks passed."
- [ ] `cd backend && pytest -q && ruff check . && ruff format --check .`
- [ ] `cd frontend && npm run typecheck && npm test && npm run build`
- [ ] `python scripts/scan_repo.py` is clean (secrets, real e-mails, passport-like numbers, TODOs).
- [ ] Every screen shows the sandbox banner (sign-in page included).
- [ ] If you will show model mode: set `LLM_PROVIDER`, `LLM_API_KEY` and a pinned `LLM_MODEL` in
      `.env`, ask one question, and confirm the "Model: ..." badge. Otherwise say "template mode".
- [ ] Freeze the code. Commit. Tag the commit you submit.

## Build and send

- [ ] `python scripts/make_submission.py` writes `dist/studyroute-submission.zip` (refuses to build
      if the scan finds a problem). Unzip it elsewhere and run it once.
- [ ] E-mail, in English, to the organisers: the archive (or a repository link), the one-page
      description, the deck and the video link or file. Use the subject format from the official
      page. Check the attachment size limit.
- [ ] Keep the sent e-mail and a backup copy of everything sent.

## Verify before you submit (blueprint section 18)

| # | Item | Status |
|---|------|--------|
| 1 | Deadline 20 Oct 23:59 Beijing (21:59 Dhaka) | Re-check on the official site |
| 2 | Submission format and deliverables | Open: rules PDF |
| 3 | Scoring rubric and weights | Open: rules PDF |
| 4 | Any mandatory API, dataset or test environment | Open: rules PDF, organiser e-mail |
| 5 | Topic C requirements | Open: rules PDF |
| 6 | Eligibility and passport pages | Open: rules PDF, registration form |
| 7 | Living-expense limit USD 2,000 a month plus 50% | Placeholder, `verified: false` |
| 8 | Single AD branch rule | Placeholder, `verified: false` |
| 9 | Circular of 30 Sep 2026 | Placeholder, read it in full |
| 10 | International card rule for education | Placeholder, `verified: false` |
| 11 | ISO purpose code for the instruction preview | Not shown on purpose, check the ISO list |
| 12 | University payment instructions (reference format, charge code) | Ask each university |
