# Botkeep — GitHub import + সম্পূর্ণ local ONNX models

## কীভাবে কাজ করে
Botkeep GitHub importer: panel-এ 20 MB total, 4 MB/file, 1,000 files limit দেখিয়েছে। তাই Git tree ছোট রাখা হয়েছে। বড় local reader/explainer model files এবং submission/media **একই GitHub repository-এর Release asset**-এ byte-exact রাখা হবে। Startup-এ checksum-verified download/extract হবে, তারপর app চলবে। Training code/data repo-তে আছে। ছোট risk/dialogue model-ও repo-তে আছে। কোনো app feature/cloud-only replacement দিয়ে সরানো হয়নি।

দুটি আলাদা ZIP:
- **StudyRoute-Botkeep-GitHub.zip**: extract করে source files GitHub-এ commit করবেন। ZIP ফাইলটি নিজে commit করবেন না।
- **StudyRoute-local-models-v1.zip**: এই নাম অপরিবর্তিত রেখে **GitHub Release attachment** হিসেবে upload করবেন। এটি repo Code/files-এ upload/commit করবেন না। এটি extract/recompress করবেন না; SHA-256 pinned আছে।

## 1. Repo আপডেট — পুরোনো বড় files যেন branch-এ না থাকে
আপনার repo: redwan786/StudyRoute-botkeep, branch: master। শুধু ছোট ZIP overlay করলে old tracked models/videos থেকে যাবে এবং importer আবার ব্যর্থ হবে।

নিরাপদ পথ: নিজের PC-তে আলাদা **fresh clone**; এতে local personal কাজ/data থাকবে না। Git installed থাকলে PowerShell:

```powershell
git clone --branch master https://github.com/redwan786/StudyRoute-botkeep.git StudyRoute-botkeep-clean
cd StudyRoute-botkeep-clean
git rm -r -- .
```

শেষ command শুধুমাত্র এই fresh clone-এ চালান; নিজের অন্য working folder-এ নয়। পুরোনো tracked files working copy থেকে সরায়; পুরোনো commits/history remote থেকে মুছে দেয় না। Clone-এর `.git` অক্ষত থাকবে।

এবার **StudyRoute-Botkeep-GitHub.zip extract করে তার ভিতরের contents** এই clone root-এ copy করুন। Root-এ main.py, model_bootstrap.py, requirements.txt, backend/, deploy/, web/ থাকবে। `.env`/private secrets copy নয়।

```powershell
git add .
python scripts/check_github_limits.py
python scripts/prepare_botkeep.py --check
git diff --cached --stat
git commit -m "Prepare Botkeep GitHub import with pinned local model Release"
git push origin master
```

Force push লাগবে না। GitHub website upload করতে চাইলে old removed paths-ও delete করতে হবে; 100-file/batch browser limit-এর কারণে Git/GitHub Desktop ব্যবহার করা সহজ। Repo public করার প্রয়োজন নেই।

নতুন repo/branch ব্যবহার করলে নিচের MODEL_GITHUB_REPO এবং Botkeep branch field actual name অনুযায়ী বদলান। Workflows master/main/botkeep নামের ওপর নির্ভর করে না।

## 2. GitHub Release publish — mandatory
GitHub repo → Releases → Draft/Create a new release:

- Tag: **botkeep-models-v1** (এই exact tag তৈরি করুন)
- Target: **master**
- Release title: StudyRoute local models v1
- Attach/upload: **StudyRoute-local-models-v1.zip**
- Upload পুরো শেষ হতে দিন, তারপর **Publish release**। Draft অবস্থায় রাখবেন না।

Models ZIP-কে Code → Add file নয়; Release attachment হিসেবে দিতে হবে। Repository archive-তে Release attachments থাকে না, তাই Botkeep ছোট source tree import করতে পারবে। ভবিষ্যতে models বদলালে নতুন pinned hashes/tag দিয়ে versioned release তৈরি করতে হবে; শুধু ZIP replace করলে integrity verification fail হবে।

## 3. Private repo হলে model download token
Botkeep GitHub App আপনার repo import করতে পারলেও app-এর Python process-এ সেই token স্বয়ংক্রিয়ভাবে পাওয়া যায় না। Private Release download-এর জন্য আলাদা least-privilege token লাগবে।

GitHub profile → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate:
- Resource owner: redwan786
- Repository access: Only select repositories → StudyRoute-botkeep
- Repository permissions: **Contents: Read-only**; Metadata-এর automatic read access রাখুন।
- Expiration নিজের policy অনুযায়ী নির্ধারণ করুন। Token expire/revoke হলে ভবিষ্যৎ model re-download ব্যর্থ হবে।

Token সরাসরি Botkeep Environment-এর **MODEL_GITHUB_TOKEN**-এ রাখুন। Chat, repo, screenshot, Release description-এ নয়। Full account/classic broad write token প্রয়োজন নেই। Organization approval লাগলে approval না হওয়া পর্যন্ত download কাজ নাও করতে পারে।

Public repo + public published Release হলে MODEL_GITHUB_TOKEN blank রাখা যায়। Private repo শুধু সুবিধার জন্য public করবেন না।

## 4. Botkeep-এর paused update clear করে সঠিক source sync
Server offline রাখুন। GitHub tab-এর পুরোনো paused import → **Cancel and restore files**। পুরোনো source না থাকলে empty runtime-ই থাকবে; এটি app upload নয়। তারপর:
- My repositories → redwan786/StudyRoute-botkeep
- Branch → master
- Check repository
- Import mode → **Merge files** (data preserve করতে destructive Replace এড়িয়ে চলুন)
- Sync repository

Sync সফল হলে linked source-এ actual commit দেখা চাই, Files root-এ main.py/model_bootstrap.py/requirements.txt থাকা চাই। পুরোনো NoobCrow repo বা botkeep branch ব্যবহার করবেন না। পুরোনো tree-এর size error আবার এলে branch-এ বড় files রয়ে গেছে কি না check_github_limits দিয়ে যাচাই করুন। Initial setup-এ Pull before Start / Restart unchecked রাখুন।

## 5. Runtime ও dependencies
- Python 3.13 (এই package স্থানীয়ভাবে 3.13-এ যাচাই করা)
- Requirements: root **requirements.txt**
- Start command: **python main.py**

Botkeep managed profile requirements install করে থাকলে duplicate action নয়। আগের empty server-এর কারণে dependencies install না হয়ে থাকলে Packages/Startup-এর install action-এ root requirements দিন। Explicit install command চাইলে:

```text
python -m pip install --no-cache-dir -r requirements.txt
```

Interactive app console-কে Linux shell ধরে এই command পাঠাবেন না। ModuleNotFoundError মানে আগে requirements installation প্রয়োজন। Node build Botkeep-এ নয়; prebuilt deploy/botkeep/site অন্তর্ভুক্ত।

## 6. প্রথম Start-এর আগে Environment

```dotenv
MODEL_GITHUB_REPO=redwan786/StudyRoute-botkeep
MODEL_GITHUB_TOKEN=
APP_ENV=sandbox
ASSISTANT_CLOUD_ENABLED=false
NLU_MODE=auto
DIALOGUE_MODE=auto
EXPLAINER_MODE=auto
RISK_MODE=auto
BOTKEEP_SEED_DEMO=true
```

Private repo হলে token field খালি নয়; panel-এর private value দিন। local models ব্যবহার করতে চাইলে LLM_PROVIDER/LLM_API_KEY operator overrides blank রাখুন; cloud provider ব্যবহার ঐচ্ছিক এবং per-user saved-key features অপরিবর্তিত। `ASSISTANT_CLOUD_ENABLED=false` local model mode বেছে নেয়—AI disable করে না।

Network-এর actual assigned application port ব্যবহার করুন। আগের screenshot-এ **41171** ছিল; একই থাকলে SERVER_PORT=41171। Injected value থাকলে সেটি রাখুন। SFTP port নয়।

Persistent writable DATA_DIR দিন/রাখুন। Default root/data। এতে SQLite, dev_secrets.json এবং downloaded model cache থাকবে। Source update-এ data মুছবেন না। Models cache থাকলে source update-এর পর cache থেকেই restore করা যায়। Backend model paths অক্ষত থাকলে startup-এ download নয়—hash verification হবে। Host-এর actual persistence/account limits deployment-এ যাচাই করতে হবে।

DATA_ENCRYPTION_KEY নিজের PC-তে তৈরি করুন:
```powershell
python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```
Output private Environment value হিসেবে রাখুন ও backup করুন। Existing database থাকলে তার original key বদলাবেন না। Matching DB + encryption key + generated secrets preserve করতে হবে।

Domains থেকে HTTPS hostname পেলে PUBLIC_ORIGIN ও CORS_ORIGINS-এ actual exact HTTPS origin দিন, path নয়। যেমন https://your-host.example একটি placeholder; নিজের hostname বসাতে হবে। Production browser login পরীক্ষা করার আগে এটি configure করুন।

## 7. Start ও checks
Start একবার দিন। First boot-এ model Release asset download + extraction হবে, তারপর model load + app startup। Large download চলার সময় HTTP listener তখনও ready নাও হতে পারে; startup timeout হলে logs দেখে platform grace period/support প্রয়োজন হতে পারে। তখন বারবার Restart নয়।

Expected messages:
- Downloading local model Release asset; first startup may take time.
- Local models installed and SHA-256 verified.
- reader/explainer/risk loaded (project logs)
- Application startup complete.

পরের startup: Local models: all committed hashes verified.

Startup source `main.py` model bootstrap ছাড়া সরাসরি অন্য API command দিয়ে চালাবেন না। Download/hash error হলে bootstrap বন্ধ হবে; silent cloud-only server চালাবে না।

HTTPS ready হলে /api/v1/health, /login/ পরীক্ষা করুন। Parent login → refresh/new tab → session restore; saved provider-key metadata; Compare, Documents, Payments, Bank network, Smart escrow ও sandbox flows পরীক্ষা করুন। Model verify command (নিজের PC/host shell available হলে): python scripts/verify_local_models.py। Health ai_mode=llm একাই সব models loaded-এর প্রমাণ নয়; loader logs/verify command দেখুন।

## Troubleshooting
- 404 model Release: exact repo/tag, published status, Contents read-only token/repository access দেখুন।
- 401/403: expired token, missing permission, organization approval বা GitHub rate limit হতে পারে।
- SHA-256/size failure: wrong/recompressed/changed asset; exact supplied ZIP upload করুন। Integrity check bypass নয়।
- main.py missing: GitHub sync/root nesting সমস্যা—startup command নয়।
- 20 MB error: model ZIP বা old model/media files এখনও branch-এ committed আছে। Git history remove/force-push নয়; current tree clean করুন।
- Model loading dependency error: complete original runtime requirements install করুন; local ONNX inference এই dependencies চায়।
- Out of memory/disk: actual usage মাপতে হবে। ছোট Git import মানে runtime RAM/disk requirement কমে যায় না। 2 GB allocation-এ install/runtime headroom Botkeep-এ যাচাই হয়নি।
- Repository source update-এর আগে private data backup; automated pull initially off রাখুন।

## Scope / validation
Original models byte-exact split across Git + Release; training code/data repo-তে এবং submission/media Release asset-এ রাখা হয়েছে। Tests/security guards বা features সরিয়ে import limit মানানো হয়নি। README-এর পুরোনো full-project hosting নির্দেশনার বদলে এই guide প্রযোজ্য।

Botkeep/GitHub accounts-এ agent upload/publish/deploy করেনি। Private live Release download platform-এ এখনও চালানো হয়নি। Local integrity/cache/download simulations এবং original model loading যাচাইয়ের ফল VALIDATION_GITHUB_MODELS.md-তে আছে।
