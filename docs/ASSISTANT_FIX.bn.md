# StudyRoute assistant fix v2 — ব্যবহার ও পরিবর্তনের নোট

## v2: বর্তমানে চলা app update করার সহজ উপায়

Screenshot-এর `what can you do?` এবং `kemon acho?` প্রশ্নে ভুল clarification response
সংশোধন করা হয়েছে। Capabilities/help-এর একাধিক phrasing, English/Bangla/Banglish wellbeing,
সংক্ষিপ্ত repeated greeting এবং সহজ assistant পরিচয় যোগ হয়েছে। এটি এখনো সীমিত offline routing;
একটি নতুন generative model বা পূর্ণ multilingual assistant তৈরি করা হয়নি।

যদি v1 fixed app ইতিমধ্যে চলছে, **নতুন clone/install/seed লাগবে না**:

- Backend terminal-এ `Ctrl+C` দাও।
- `StudyRoute-assistant-v2-update.zip`-এর contents বর্তমান project root-এ overlay করো।
  এই incremental update-এ শুধু backend source/tests ও documentation আছে।
- Backend আবার চালাও:

```powershell
cd "E:\ETC\FinTech\Working\StudyRoute\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

- Frontend চলতে পারে; `http://localhost:3000`-এ `Ctrl+Shift+R` দিয়ে নতুন conversation শুরু করো।
- `what can you do?`, `kemon acho?`, `tumi ki ki korte paro?` এবং পরপর `hello`, `hi` পরীক্ষা করো।
- `.env`, `.venv`, database বা node_modules মুছবে না। আগের local edits থাকলে আগে diff/backup রাখবে।

নিচের বিস্তারিত নির্দেশনা সম্পূর্ণ source copy বা প্রথম setup-এর জন্য।

## কী সমস্যা ছিল

`hello`, `what is it?` এবং অজানা প্রশ্ন একই `HELP` handler-এ গিয়ে একই paragraph ফেরত দিত।
Frontend সাধারণ কথোপকথনের আগের প্রশ্ন পাঠাত না; শুধু payment task-এর `pending` values রাখত।
Trained reader intent/slots বোঝে, কিন্তু নিজে নতুন বাক্য লেখার generative model নয়।

## কী বদলেছে

- Greeting, app overview, getting started, assistant identity, thanks, KYC explanation/help,
  transfer-cost explanation, smart escrow, bank network ও audit guidance-এর আলাদা read-only routes।
- বর্তমান account-এর KYC status ও quote/payment-এর সংখ্যা আগের মতো engine facts থেকে আসে।
- `What is my KYC status?` → `how do I fix it?` → `tell me more`-এ topic ধরে উত্তর।
- সর্বশেষ সর্বোচ্চ ছয়টি user question পাঠানো হয়; প্রতিটির সীমা এক হাজার characters।
  এগুলো শুধু topic hint, কোনো amount/date, payment ID, permission বা approval-এর প্রমাণ নয়।
  Assistant-এর generated reply history হিসেবে পাঠানো হয় না।
- অস্পষ্ট প্রশ্নে clarification, reader চিহ্নিত out-of-scope প্রশ্নে সৎ সীমাবদ্ধতা।
- Sidebar-এ `Offline assistant` label; diagnostics-এ effective intent ও reader suggestion আলাদা।
- Next.js `web/` ও পুরোনো Vite `frontend/`—দুই client-এ history সংযুক্ত।
- Policy checks, number guard, quote ownership, audit, MFA ও human-only approval সরানো হয়নি।
  পুরোনো API client history না পাঠালেও কাজ করে। Dependencies/schema/database migration বদলায়নি।

## গুরুত্বপূর্ণ সীমা

এটি API key ছাড়া ব্যবহারযোগ্য, সীমিত offline assistant—ChatGPT-এর মতো সাধারণ বিষয় নিয়ে
অসীম free-form chat নয়। সাধারণ app/finance প্রশ্নে reviewed guidance, ব্যক্তিগত status ও
হিসাবে engine facts ব্যবহার করে। Bangla greeting, wellbeing ও capability-এর কিছু Banglish phrasing চেনে; পূর্ণ multilingual
conversation দাবি করা হচ্ছে না। আগের external-LLM configuration অক্ষুণ্ণ আছে, কিন্তু এই fix-এর
জন্য কোনো key লাগে না। External provider call এই delivery-তে বাস্তবে পরীক্ষা করা হয়নি।

## এখন তোমার Windows project-এ বসানো

আগের project-এর backup রাখো। Backend ও frontend-এর running terminal-এ `Ctrl+C` দাও।

**Patch ZIP সবচেয়ে সহজ:** এর ভেতরের `backend`, `web`, `frontend`, `docs` path-গুলোর files
তোমার বিদ্যমান project root-এ overlay করো। পুরো folder আগে delete করবে না।
`.env`, `backend/data`, `.venv`, `node_modules` বা নিজের অন্য কাজ মুছবে না।
অন্য কোনো source edit করে থাকলে সংশ্লিষ্ট changed files আগে diff করে নাও।

PowerShell দিয়ে overlay করতে পারো; download অন্য জায়গায় হলে প্রথম path বদলাবে:

```powershell
Expand-Archive -LiteralPath "$HOME\Downloads\StudyRoute-assistant-fix-patch.zip" -DestinationPath "E:\ETC\FinTech\Working\StudyRoute" -Force
```

Backend terminal:

```powershell
cd "E:\ETC\FinTech\Working\StudyRoute\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

আলাদা frontend terminal:

```powershell
cd "E:\ETC\FinTech\Working\StudyRoute\web"
npm run dev
```

Browser-এ `http://localhost:3000` খুলে `Ctrl+Shift+R` দাও। পুরোনো chat view থাকলে page reload করবে।
আগের SQLAlchemy workaround আবার করার দরকার নেই; virtual environment ও installed packages অপরিবর্তিত।
`seed` আবার চালানো, `npm audit fix --force`, database reset বা dependency reinstall দরকার নেই।

Full source ZIP-ও দেওয়া হয়েছে। এটি নতুন clean copy; তোমার স্থানীয় `.env`, installed packages ও
runtime database এতে নেই। চলমান local project-এ patch overlay-ই সহজ। Git-এ নিজের branch-এ diff
দেখে commit করবে; `.env`, `.venv`, database ও `node_modules` commit করবে না।

## নিজে যাচাই

নতুন করে page load করে assistant-এ এই প্রশ্নগুলো দাও:

- `hello` — greeting ও কী সাহায্য দরকার সেই প্রশ্ন।
- `what is it?` — StudyRoute overview, greeting-এর পুনরাবৃত্তি নয়।
- `What is my KYC status?` — account-এর আসল simulated status।
- `how do I fix it?` — mock documents-এর নির্দেশনা।
- `tell me more` — KYC-এর ব্যাখ্যা।
- `What are transfer fees?` — fee ও FX margin ব্যাখ্যা।
- `What is smart escrow?` — simulation-এর সঠিক পরিচয়।
- Compare screen-এ quote খুলে `Why is Provider B cheaper than A?` — engine-এর quote breakdown।

কোনো প্রশ্নে assistant নিজে payment approve/submit বা real money transfer করবে না।

## Developer validation

Automated coverage includes distinct replies, chained follow-ups, stale-topic barriers,
strict history bounds/types, untrusted history, policy refusal, number provenance, real trained
reader integration, and frontend history serialization. Existing financial/approval tests retained.
See `ASSISTANT_FIX_TESTS.md` for the final validation results.
