# StudyRoute — GitHub `botkeep` branch থেকে deploy

এই release আপনার নতুন StudyRoute.zip থেকেই তৈরি। নতুন UI, explainer/risk models ও project features রাখা হয়েছে। `.git`, real `.env`, database, generated private secrets, node_modules, Python venv ও build caches নেই। GitHub account বা Botkeep account-এ agent push/deploy করেনি।

## 1. কোন ZIP ব্যবহার করবেন
**StudyRoute-botkeep-branch.zip** → `botkeep` Git branch-এর জন্য সম্পূর্ণ project। `deploy/botkeep/site/`-এ prebuilt frontend অন্তর্ভুক্ত; এটিও commit করতে হবে। Botkeep-এ শুধু Python runtime লাগবে।
এই ZIP-এর enclosing StudyRoute folder Git repository root-এর সঙ্গে মেলান; ভিতরে আরেকটি StudyRoute/ তৈরি করবেন না।

## 2. নিরাপদে branch তৈরি
Existing local project-এ নিজের পরের changes থাকলে আগে backup/commit করুন। সবচেয়ে পরিষ্কার পথ নতুন clone:

```powershell
git clone https://github.com/NoobCrow/StudyRoute.git StudyRoute-botkeep
cd StudyRoute-botkeep
git switch -c botkeep
```

যদি remote-এ botkeep branch আগেই থাকে, নতুন branch command-এর বদলে:

```powershell
git fetch origin
git switch --track origin/botkeep
```

ZIP extract করুন। Extracted `StudyRoute`-এর **ভিতরের contents** এই clone folder-এ copy/replace করুন। Clone-এর নিজের `.git` রাখবেন; original project-এর `.git` বা real `.env` copy করবেন না। নতুন clone-এর root-এ main.py, requirements.txt, backend/, web/, deploy/ থাকবে।
তারপর:

```powershell
python scripts/prepare_botkeep.py --check
git status --short
git add .
git diff --cached --stat
git commit -m "Prepare StudyRoute for Botkeep GitHub deployment"
git push -u origin botkeep
```

নতুন clone-এ ignored private files না থাকলে git add . public release-ই stage করবে। Existing working folder ব্যবহার করলে আগে নিশ্চিত করুন `.env`, data/, .venv/, node_modules/ tracked নয়। `git ls-files .env` কোনো path দেখালে push করবেন না; আগে file untrack করুন ও প্রয়োজন হলে exposed credential rotate করুন। কখনো force-push/পুরোনো history overwrite প্রয়োজন নেই।

**GitHub website-এ ZIP ফাইলটি শুধু upload করলেই deploy হবে না। Source contents commit করতে হবে।** বড় model files browser upload limit ছাড়াতে পারে; Git push ব্যবহার করুন।

## 3. Botkeep → GitHub connection
New/Create → Python application → GitHub source। Botkeep GitHub App চাইলে কেবল প্রয়োজনীয় StudyRoute repository access দিন।

| Field | Value |
|---|---|
| Repository | NoobCrow/StudyRoute |
| Branch | botkeep |
| Root directory | repository root — blank অথবা panel অনুযায়ী `.` |
| Python | 3.12; available 3.13-এও dependency compatibility যাচাই করতে পারেন |
| Requirements file | requirements.txt |
| Start command | python main.py |

অতিরিক্ত install command চাইলে:

```text
python -m pip install --no-cache-dir -r requirements.txt
```

Managed Python profile requirements নিজে install করলে duplicate install command দেবেন না। **Node start command, npm run dev, Docker Compose বা backend/ root নির্বাচন করবেন না।** Root requirements.txt backend lockfile-কে reference করে।

## 4. Network এবং HTTPS
Network-এ assigned HTTP port দেখুন। Botkeep-এর injected SERVER_PORT থাকলে সেটি রাখুন। না থাকলে ওই actual port Environment-এর SERVER_PORT-এ দিন; 8000 অনুমান করবেন না। App 0.0.0.0-তে bind করে।
Domains-এ ওই port route করে provided alias বা নিজের verified domain configure করুন। HTTPS ready করুন। Final browser URL-এর origin লিখে রাখুন, যেমন https://your-real-host.example — এটি placeholder, সত্যি hostname নয়।

## 5. প্রথম Start-এর আগে Environment
`deploy/botkeep/environment.example`-এর template দেখুন। অন্তত:

```dotenv
APP_ENV=sandbox
PUBLIC_ORIGIN=https://YOUR-ACTUAL-HOSTNAME
CORS_ORIGINS=https://YOUR-ACTUAL-HOSTNAME
ASSISTANT_CLOUD_ENABLED=true
BOTKEEP_SEED_DEMO=true
SHOW_DEMO_HINTS=true
```

PUBLIC_ORIGIN/CORS_ORIGINS-এ final actual HTTPS origin দিন, `/login`/অন্য path নয়। Auto-start হলে variables configure করার আগে Stop রাখুন।

### Database / encryption
- Panel আলাদা persistent writable path দিলে সেটি DATA_DIR-এ দিন। Default root/data/; source update/restart-এ এই path preserved হচ্ছে কি না পরীক্ষা আবশ্যক।
- DATABASE_URL blank রাখলে DATA_DIR-এর SQLite ব্যবহার হবে।
- প্রথম নতুন installation-এর আগে নিজের PC-তে:

```powershell
python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Output **DATA_ENCRYPTION_KEY**-এ panel Environment-এ রাখুন। Chat/screenshot/GitHub-এ নয়। এই secret স্থির ও privately backed up রাখুন। Already used database থাকলে নতুন key generate করে পুরোনোটি replace করবেন না।
- Sandbox JWT ও webhook secrets data/dev_secrets.json-এ persist হবে। Database-এর সঙ্গে matching secrets রাখতে হবে; বদলালে login/saved-key recovery ভাঙবে।
- Source update যেন data/ delete/replace না করে। Botkeep-এর destructive clean/reinstall operation আলাদা; backup ছাড়া ব্যবহার করবেন না।

### AI provider
Per-user key চাইলে LLM_PROVIDER এবং LLM_API_KEY blank রেখে login-এর পর assistant → উপরের AI connection settings → Gemini/Groq → key + consent → connect করুন। Password field আবার blank হওয়া স্বাভাবিক; saved metadata দেখুন। এটি encrypted server database-এ রাখা হয়, browser storage-এ নয়। নতুন hosting-এ local key স্বয়ংক্রিয়ভাবে যায় না; একবার save করতে হবে।

Operator Gemini ব্যবহার করতে চাইলে panel-এ LLM_PROVIDER=gemini, LLM_MODEL=gemini-2.5-flash এবং নিজের LLM_API_KEY দিন। HF Space চাইলে LLM_PROVIDER/LLM_API_KEY blank, HF_SPACE_URL/HF_TOKEN/HF_SPACE_APP_SECRET দিন। Secrets কখনো NEXT_PUBLIC variable-এ নয়।
কোনো provider configure না থাকলে Cloud unavailable দেখাবে; app model connection বানিয়ে দেখাবে না। Explicit offline demo-তে ASSISTANT_CLOUD_ENABLED=false করা যায়। Your supplied source-এর local explainer/risk features রাখা হয়েছে। Quota/429 app patch বাড়াতে পারে না।

## 6. Start এবং পরীক্ষা
Start → Console-এ requirements install ও startup দেখুন। তারপর actual HTTPS hostname-এ:
- /api/v1/health → status ok
- /login/ → StudyRoute sign-in

Unchanged sandbox demo accounts: parent@demo.studyroute.test / student@demo.studyroute.test। Initial default password Sandbox#2026, sandbox MFA 246810। Operator SEED_DEMO_PASSWORD initial seed-এর আগে set করলে সেটিই ব্যবহার হবে; পরে variable বদলালে existing password স্বয়ংক্রিয়ভাবে বদলায় না।

পরীক্ষা করুন:
1. Login → refresh → same-origin নতুন tab: session restore।
2. Save key → refresh: saved provider metadata।
3. Workload stop/start: saved account data/provider remains।
4. English question/Bengali question: current-turn language। Live provider compliance পরীক্ষা করতে হবে।
5. Compare এবং simulated payment flow।

## 7. ভবিষ্যৎ updates — GitHub থেকেই
Backend-only changes: commit/push botkeep → Botkeep GitHub tab থেকে source update/pull → Restart। Botkeep redeploy মানেই GitHub pull নয়; console/commit যাচাই করুন। Auto-pull/start কেবল panel-এ explicit enable করলে ধরে নেবেন।

Frontend বদলালে compiled site-ও update করুন। নিজের PC-তে Node 24 দিয়ে:

```powershell
npm ci --prefix web
npm run build --prefix web
python scripts/prepare_botkeep.py
python scripts/prepare_botkeep.py --check
git add web deploy/botkeep/site deploy/botkeep/site-manifest.json
git commit -m "Update Botkeep frontend"
git push origin botkeep
```

অথবা GitHub → Actions → **Rebuild Botkeep frontend** → Run workflow → branch botkeep। Workflow tests/build চালিয়ে শুধু public frontend files branch-এ commit করবে; repository workflow write permission/branch protection allow করতে হবে। এরপর Botkeep source update/restart করুন। এই workflow manual, নিজে থেকে আপনার account-এ চালানো হয়নি।

**Botkeep committed frontend check** workflow source/site hash মিলিয়ে stale site ধরবে। initial package-এ frontend আগে থেকেই build করা; প্রথম deploy-তে এই rebuild লাগবে না।

## 8. Troubleshooting / safety
- Frontend missing → branch ভুল, prebuilt deploy/botkeep/site commit হয়নি, বা root backend/ দেওয়া হয়েছে।
- 502 → actual port/listener/domains routing ও Console শেষ error lines দেখুন।
- Browser auth 403 → PUBLIC_ORIGIN actual URL-এর exact origin কি না; wildcard CORS দিয়ে bypass নয়।
- Key নেই → অন্য account, নতুন DB, changed DATA_DIR অথবা overwrite কি না। Wrong encryption key হলে matching private backup restore করুন।
- Disk → total 2 GB plan হলে packages+files+data মাপুন; pip no-cache রাখুন, Node build এখানে নয়। Database/secret delete করে space মুক্ত করবেন না।
- Local source ZIP-এ real .env ছিল; release-এ রাখা হয়নি। সেটি কোথাও public হয়ে থাকলে সংশ্লিষ্ট credentials rotate করুন; এই কাজ private secret expose হয়েছে এমন দাবি নয়।
- Shared demo account-এ valuable personal API key রাখবেন না। একই account-এর অন্য user quota ব্যবহার করতে পারে। Restricted demo key, separate account বা access protection ব্যবহার করুন।
- Beta hosting / sandbox only, real money/real identity documents নয়। Completed panel backup + independent private backup রাখুন।

## Official references
https://botkeep.cloud/docs/hosting
https://botkeep.cloud/docs/github
https://botkeep.cloud/docs/python
https://botkeep.cloud/faq
https://botkeep.cloud/terms
