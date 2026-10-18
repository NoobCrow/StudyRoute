# What to send, and how to rebuild it

The organiser's e-mail of 15 October 2026: items 1 and 2 are **mandatory**, the rest are optional.
Send the e-mail soon: they asked for submissions "as soon as possible", and a later version replaces an
earlier one.

| # | Item | File | Send as |
|---|------|------|---------|
| 1 | Technical documentation (mandatory; 13 pages with a cover and a business-case summary) | `submission/StudyRoute_Technical_Documentation.pdf` | attachment |
| 2 | Presentation deck, 13 slides, about 8.4 minutes of notes (mandatory) | `submission/StudyRoute_Deck.pptx` | attachment |
| 3 | Demo video, 5 minutes (optional) | the team's voiced pitch video; interim silent video: `submission/StudyRoute_Demo.mp4` | link (or attachment if small) |
| 4 | Source code, README, GitHub link (optional) | https://github.com/NoobCrow/StudyRoute (must be public); archive `dist/studyroute-submission.zip` (82 MB) | link |
| 5 | Security self-assessment (optional) | `submission/StudyRoute_Security_Self_Assessment.pdf` | attachment |
| 6 | Execution evidence (optional) | `submission/StudyRoute_Execution_Evidence_Summary.pdf` and a zip of `submission/evidence/` | attachments (about 0.5 MB) |

`dist/send/` (not tracked by git; about 3 MB) holds items 1, 2, 5 and 6 under numbered names: the folder to drag
into the e-mail. To rebuild it, copy the four files above under those names and zip `submission/evidence/` (as
`evidence/`) together with `StudyRoute_Execution_Evidence_Summary.pdf` into `6_StudyRoute_Execution_Evidence.zip`.

The three PDFs (technical documentation, security self-assessment, execution evidence summary) are made from
their Markdown files, each with a cover page whose numbers are read from the repository. If a document
changes, regenerate them before sending (needs Google Chrome):

```bash
pip install markdown
python scripts/make_pdfs.py
```

The deck must be rebuilt with the team name and link:

```bash
cd submission/deck
TEAM_NAME="TeamEkxin" REPO_LINK="https://github.com/NoobCrow/StudyRoute" node build_deck.js
```

(A plain `npm run build` puts "[Team name]" and "[repository link]" back into the deck. `python
scripts/preflight.py` flags it.)
