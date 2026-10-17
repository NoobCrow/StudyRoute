# Competition rules, and how StudyRoute meets them

Source: **"PBCSF Appendix 2: Problem Description and Competition Rules for International Track"**,
2026 Shenzhen International FinTech Competition (the 8th FinTechathon), WeBank FinTech College
Students Challenge. The PDF was supplied by the team on 17 October 2026 and is reproduced below for
reference, in the organisers' words. The organisers' website is the authority and may change:
https://fintechathon.g-ican.com

Part 1 is the rules. Part 2 is our own check of them: for each requirement, what we did and where the
evidence is. "Not done" means exactly that.

---

## Part 1. The rules (reproduced)

### Theme

The theme of this year's International Track is **"AI as a Financial Participant"**: each team
designs and builds an AI agent capable of completing real tasks in a financial scenario. Choose one of
the six topics below.

### Topics (choose one of six)

| Topic | Name | What it asks for |
|-------|------|------------------|
| A | Personal Finance Assistant | An intelligent assistant for individual users, capable of smart budgeting, bill analysis, and spending insights, delivering actionable recommendations based on the user's income and expenses. |
| B | Wealth Advisory Agent | An agent that mirrors a professional wealth-advisory workflow (product comparison, client risk profiling, and advisory dialogue), producing compliant and explainable asset-allocation suggestions. |
| **C** | **Cross-border & Student Finance Assistant** | **Solutions addressing real financial pain points of international students and cross-border users, such as remittances, tuition payments, credit building, and multi-currency management.** |
| D | Insurance Assistant | An insurance-scenario assistant capable of policy Q&A, coverage-gap analysis, and claims guidance, helping users understand and manage their insurance portfolios. |
| E | SME Finance Copilot | A finance copilot for small-business owners, offering financing-option matching, cash-flow management with alerts, and business financial analysis. |
| F | Agent Wallet | Autonomous On-chain Wallet: the track's signature topic. Build an AI wallet agent that autonomously executes on-chain operations (asset management, transaction execution, risk control). Ambitious ideas are encouraged, with a 0 to 5 point challenge bonus. |

### Unified requirements and scoring

All six topics share the same core capability requirements and scoring criteria; choosing the
on-chain topic does not affect scoring.

| Criterion | Weight |
|-----------|--------|
| Task completion | **40%** |
| Security & compliance | **30%** |
| Innovation & interaction | **30%** |
| Challenge bonus (on-chain exploration) | 0 to 5 points |

### Eligibility and teaming

**Who may enter.** The Competition is open to full-time students (including undergraduates, master's
and doctoral candidates) currently enrolled at overseas universities and research institutions, with
60% non-Chinese nationals, major, or year of study. For the purposes of these Rules, "overseas
universities" refers to higher education institutions and research organizations established in
countries other than China (including regions outside Mainland China, Hong Kong SAR, Macao SAR, and
Chinese Taipei) that hold independent accreditation and are authorized to independently confer
academic qualifications or degrees.

**Teaming.** Teams of 2 to 5 students; cross-year, cross-major, cross-university teaming (including
cross-border collaborations) is welcome, provided that all team members are from institutions outside
Mainland China, Hong Kong SAR, Macao SAR, and Chinese Taipei. Each participant may join only one team
across both the Domestic and International Tracks; duplicate registration is invalid.

**Language.** English is the official language of the International Track; submissions,
presentations, and reviews are all conducted in English.

> Note: To ensure the international character of this track, at least 60% of a team's members should be
> non-Chinese nationals. Track assignment is determined by the organizer based on members'
> nationalities and institutions.

### Submission

Registration and submission share the same deadline: **October 20, 2026, 23:59 (Beijing Time, UTC+8)**,
that is 15:59 UTC, 17:00 London (BST), 09:00 US Pacific (PDT), 01:00 Tokyo (Oct 21), 03:00 Sydney
(Oct 21). A bilingual email reminder will be sent 24 hours before the deadline.

| # | Deliverable | What the rules say |
|---|-------------|--------------------|
| 01 | Technical documentation | system architecture, core algorithm description, security design |
| 02 | Presentation deck | final presentation no longer than 10 minutes |
| 03 | Demo video | optional, no longer than 5 minutes |
| 04 | Source code | with README, GitHub repository link, deployment instructions, and test cases |
| 05 | Security self-assessment report | permission-tier implementation and known-risk list |
| 06 | Execution evidence | for non-on-chain topics: simulated-account/sandbox operation logs and demo video; for the on-chain topic: real on-chain transaction hashes |

Submissions may be updated any time before the deadline; the latest version received prevails. No
changes are accepted after the deadline.

### Review and Grand Final

| Date | Step |
|------|------|
| October 20 | Online review by a panel of WeBank industry experts and university scholars |
| October 31 | Finalists announced |
| November 20 | Check-in and WeBank HQ visit, Shenzhen |
| November 21 to 23 | Grand Final and Awards Ceremony, Shenzhen |

At least one member of each finalist team must attend in person; a team absent without valid
justification forfeits eligibility for awards.

### Fees and benefits

- No registration fee.
- For invited finalist members, accommodation and round-trip international travel during the finals
  are arranged and covered by the organizer (number of invited members per team as stated in the
  invitation).
- International Track prize pool: RMB 250,000. First Prize RMB 100,000 (1), Second Prize RMB 80,000
  (1), Third Prize RMB 50,000 (1), Best Innovation Award RMB 20,000 (1), Excellence Awards (several);
  all prizes are pre-tax.
- Outstanding teams receive fast-track interview access to WeBank.

### Integrity and IP (key points)

Entries must be completed independently, free of plagiarism or IP infringement; third-party data,
code, and open-source components must be properly licensed. The IP in entries remains with the
contestants; the hosts may use entries and team information for non-commercial promotional purposes
(non-exclusive, royalty-free). Full terms are governed by the Competition Rules and Privacy Policy
published on the official website.

### Contact

Website: fintechathon.g-ican.com. E-mail: wangyr@pbcsf.tsinghua.edu.cn

---

## Part 2. Our check against the rules (17 October 2026)

### Entry and eligibility

| Requirement | Status | Evidence or what is left |
|-------------|--------|--------------------------|
| Topic C chosen | Done | Entry title **StudyRoute**; every document names Topic C |
| Team of 2 to 5 | Done on paper | **TeamEkxin**, four members: Farhan Labib (leader), Md Redwan Hossen, Alim Bin Yeasin, Kalvin Chakma |
| Full-time students at a university outside the excluded regions | Done on paper | All four at Ahsanullah University of Science and Technology, Bangladesh (proof of enrolment was sent with the registration; it is not stored in this repository) |
| 60% non-Chinese nationals | Done on paper | Nationalities are on the registration form (not stored here). The wording "60% non-Chinese nationals, major, or year of study" can be read more than one way: see `docs/OPEN_QUESTIONS.md`, section A, row 10 |
| One team per person | Believed | Each member joined only this team: for the team to confirm |
| Registered by 20 Oct, 23:59 Beijing (21:59 Dhaka) | **Done** | E-mail sent 15 Oct 2026, 21:25 (see `submission/REGISTRATION.md`). **The organiser's confirmation of the slot has not been seen**: ask again if none has arrived |
| English for submissions, presentation and review | Done | All submitted documents are English. The extra Bengali guides from a teammate (`docs/*.bn.md`) are not part of the submission |
| A member can attend the final in Shenzhen if invited | Open | The team must decide who, and check the Chinese visa lead time (finalists are announced 31 Oct, check-in 20 Nov) |

### The six deliverables

| # | Deliverable | Status | Where |
|---|-------------|--------|-------|
| 01 | Technical documentation | Done | `docs/TECHNICAL_DOCUMENTATION.md` (architecture, algorithms, security design) |
| 02 | Presentation deck, 10 minutes at most | Done | `submission/StudyRoute_Deck.pptx`: 12 slides, speaker notes of about 8.9 minutes. Rehearse it |
| 03 | Demo video, 5 minutes at most | **Not done** | Script ready: `submission/VIDEO_SCRIPT.md` (about 4:25). The video must still be recorded; rule 06 also asks for it |
| 04 | Source code, README, GitHub link, deployment instructions, test cases | Mostly done | README and `docs/DOCKER.md` for deployment; `docs/TEST_CASES.md` (1,652 backend, 462 web and 24 browser tests, last run 18 Oct 2026). **The GitHub repository is private**: judges cannot open the link until it is made public or shared. Latest work is not yet pushed |
| 05 | Security self-assessment, permission tiers and known risks | Done | `docs/SECURITY_SELF_ASSESSMENT.md` (risks R1 to R50) and `docs/SECURITY_TESTING.md` |
| 06 | Execution evidence: sandbox logs and demo video | Logs done, video not done | `submission/evidence/` (operation log, audit log and its verification, payments, tamper demo, security probes) |

### What each scoring criterion rests on

| Criterion | Weight | What we offer | Where |
|-----------|--------|---------------|-------|
| Task completion | 40% | One sentence becomes a quote, a ranking, a deadline plan and a draft; a human approves with MFA; a simulated provider settles; a tracker and a sealed compliance report follow. The 14-step demo passes end to end, and 24 blueprint scenarios map to tests. Topic C coverage: remittances and tuition end to end; multi-currency only as simulated accounts; **credit building is not built** | `submission/evidence/`, `docs/TEST_CASES.md`, `python -m app.scripts.demo_flow` |
| Security & compliance | 30% | The AI can never approve or move money; approval needs a fresh MFA proof bound to the summary hash; idempotency; signed webhooks; a hash-chained audit log with an outside anchor; encrypted account numbers and document text; cookie sessions; strict CSP. Attack, brute-force, data-leak, man-in-the-middle and TLS probes pass. Regulatory values are placeholders marked "Not verified". There has been no independent penetration test | `docs/SECURITY.md`, `docs/SECURITY_TESTING.md`, `docs/SECURITY_SELF_ASSESSMENT.md` |
| Innovation & interaction | 30% | True-total-cost ranking with a short-payment warning; backward deadline planning; currency-drop stress test; a student guide with a live budget slider; a trained reader and a small reinforcement-learning dialogue policy (both measured, with limits stated); an animated, accessible interface | `docs/AI_AGENT.md`, `docs/AI_EVALUATION.md`, `docs/AI_RL.md`, `web/README.md` |

### Integrity and independent work

| Requirement | Status | Evidence or what is left |
|-------------|--------|--------------------------|
| Third-party code, data and open-source parts are licensed | Done | `docs/THIRD_PARTY.md` (generated; no unknown licences) |
| The work is the team's own | The team's to confirm | Each member should be able to explain the part they built; see `submission/QA_PREP.md`, question 10, for the questions to prepare |

### Timeline we are working to

| Date | Step |
|------|------|
| 17 Oct (Sat) | Commit and push; make the repository public; retake screenshots |
| 18 Oct (Sun) | Record the demo video; one real model call saved as evidence (the AI chat owner) |
| 19 Oct (Mon), evening Dhaka | **Internal target**: rebuild the archive, tag the commit, send the final e-mail |
| 20 Oct, 21:59 Dhaka | **Hard deadline** (23:59 Beijing) |
