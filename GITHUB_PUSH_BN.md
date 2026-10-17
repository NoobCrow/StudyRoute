# GitHub-এ নিরাপদে push করার নির্দেশনা

এই release আপনার দেওয়া source থেকে তৈরি। `node_modules`, `.venv`, `.git`, database, `.env`, পুরোনো
credential store এবং build cache ইচ্ছাকৃতভাবে বাদ দেওয়া হয়েছে। **এগুলো source code-এর অংশ নয়**;
`npm ci` / `pip install` দিয়ে dependencies পুনরায় install হবে। Model weights, configuration,
contracts, tests, docs এবং submission files রাখা হয়েছে।

## ১. সবার আগে exposed credentials revoke/rotate করুন

বড় original ZIP-এ non-placeholder Hugging Face credentials ও generated application secrets ছিল।
তাদের কোনো value এই release-এ কপি করা হয়নি। কিন্তু ZIP পরিষ্কার করলেই আগের credential নিরাপদ হয় না।

- Hugging Face account থেকে পুরোনো access token revoke করে প্রয়োজনীয় minimum-permission token নিন।
- Deployed Space/app-এর app secret বদলান এবং সংশ্লিষ্ট service restart করুন।
- আগে deploy করা signing/webhook secrets থাকলে controlled rotation করুন; JWT rotation-এ পুরোনো
  sessions invalid হতে পারে। **Encryption key হঠাৎ replace বা `dev_secrets.json` delete করবেন না**:
  পুরোনো encrypted data অপাঠ্য হতে পারে। Backup, migration/re-encryption plan ছাড়া করবেন না।
- Local demo-এর নতুন data directory-তে app নতুন sandbox keys তৈরি করবে। পুরোনো production data touch করবেন না।
- কখনো credentials chat, GitHub commit, screenshot বা competition ZIP-এ দেবেন না।

## ২. Existing repository backup ও branch

Git Bash-এ আপনার আগে clone করা repository folder-এ যান। Uncommitted কাজ থাকলে আগে local backup করুন।
অন্য teammate-এর কাজ বা `.git` folder delete করবেন না।

```bash
git status
git switch -c competition-hardening-v2-2026-10-17
```

ZIP-এর `studyroute` folder-এর ভিতরের files আপনার repository root-এ **overlay/copy** করুন। Hidden
`.github`, `.gitignore`, `.dockerignore` files-ও copy হবে। ZIP-এর root folder-কে আরেকটি nested
`studyroute` subfolder হিসেবে commit করবেন না। Existing `.env` বা database copy করবেন না।

```bash
python scripts/scan_repo.py
git diff --stat
git diff --check
git status --short
```

আগের `.env`, generated keys, database বা cache যদি Git-এ tracked হয়ে থাকে, আগে tracking থেকে সরাতে হবে;
শুধু `.gitignore` যোগ করলে পুরোনো tracked files untrack হয় না। File local-এ রাখার প্রয়োজন থাকলে:

```bash
git rm --cached --ignore-unmatch .env backend/data/dev_secrets.json
```

এটি history থেকে secrets মুছে দেয় না। **Rotation আগে**; তারপর GitHub-এর sensitive-data-removal guidance
অনুযায়ী teammate-দের সঙ্গে coordinated history cleanup করুন। Blind force-push করবেন না।

## ৩. Test ও commit

Backend dependencies install করে `backend` থেকে `pytest`; web-এ `npm ci`, `npm test`,
`npm run typecheck`, `npm run build` চালান। অথবা `docker compose up --build` দিয়ে sandbox চালান।
Docker এই repair environment-এ পুনরায় চালানো যায়নি; পুরোনো Docker logs current verification নয়।

```bash
git add .
git diff --cached --stat
python scripts/scan_repo.py
git commit -m "Add institution route guards and reproducible hardening evidence"
git push -u origin competition-hardening-v2-2026-10-17
```

তারপর Pull Request খুলুন। Review ও CI pass হওয়ার পরে `main`-এ merge করুন। GitHub browser-এর
“Upload files” দিয়ে শত শত file upload করার বদলে Git ব্যবহার করুন। কোনো force-push প্রয়োজন নেই।

## ৪. Submission-এর আগে মানুষের কাজ

- `submission/REGISTRATION.md` ও deck-এ inherited team/name/affiliation সঠিক কি না যাচাই করুন।
  এগুলো repository fork করলেই আপনার পরিচয় হয় না। আমি অনুমান করে নাম বদলাইনি।
- Source provenance ও original authorship যাচাই করুন (`docs/PROVENANCE.md`)।
- Private repository-তে judges-এর access নিশ্চিত করুন; URL দিলেই access হয় না।
- বাস্তব bank quote / user study না করা পর্যন্ত সেগুলো হয়েছে বলবেন না।
- `docs/RELEASE_FIXES.md` এবং নতুন evidence index পড়ুন। 85+/100 কোনো verified result বা guarantee নয়।


## v2 upgrade — পুরোনো data না মুছে
Backend startup নতুন `recipient_institutions` table যোগ করে; existing recipient, encrypted account
বা payment মুছতে হবে না। Update-এর আগে backup নিন। পুরোনো version-এ ফিরলে নতুন table না মুছেও
পুরোনো code চলতে পারে, কিন্তু route guard থাকবে না। Upgrade/rollback staging-এ যাচাই করুন।
Frontend build আবার করুন; পুরোনো exported assets দিয়ে v2 declaration UI দেখা যাবে না।
`docs/HARDENING_V2.md`-এ current evidence পড়ুন; v1 reports v1-এর historical verification।
