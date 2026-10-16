# StudyRoute Cloud Assistant — ব্যবহার ও সেটআপ

## কী তৈরি হয়েছে, কী এখনও হয়নি

- Gemini ও Groq-এর remote LLM adapter, authenticated connection test, দুই UI-তে password key input।
- নিজের Hugging Face Gradio ZeroGPU Space-এর HTTP/SSE adapter ও deploy করার source।
- API key না দিলে configured HF Space; key দিলে নির্বাচিত Gemini/Groq model।
- quota/service/guard failure-এ স্পষ্ট message। নতুন cloud path-এ canned answer লুকিয়ে চালু নয়।
- কথার context: আগের সর্বোচ্চ ছয়টি message, server-এ masked ও untrusted হিসেবে চিহ্নিত।
- হিসাব engine-এ, payment approval মানুষের হাতে। LLM সরাসরি payment চালায় না।

**কিন্তু তোমার HF account-এ Space deploy করা হয়নি; real provider key দিয়ে live test-ও করা হয়নি।**
সংযুক্ত পরীক্ষাগুলো mocked HTTP ও local UI পরীক্ষার প্রমাণ, real model quality/availability-এর প্রমাণ নয়।
এটাকে এখনই fully deployed বা production-ready service বলা হচ্ছে না।

## পুরোনো project-এ update — আবার clone/সব install দরকার নেই

1. চলমান backend ও UI terminal-এ Ctrl+C চাপো। Project-এর backup রাখো।
2. `StudyRoute-cloud-assistant-update.zip` extract করে ভিতরের `StudyRoute` folder-এর
   **contents** বর্তমান `E:\ETC\FinTech\Working\StudyRoute` folder-এ merge/replace করো।
   ভিতরে আরেকটি StudyRoute folder বানিয়ে ফেলো না: `backend/app/ai/cloud.py` সঠিক জায়গায় থাকবে।
3. তোমার `.env`, `.venv`, `backend/data`, `node_modules` delete বা replace কোরো না।
   Patch-এ শুধু `.env.example` আছে, আসল `.env` নেই। Database migration/reseed দরকার নেই।
4. Project root `.env`-এ এই setting যোগ/আপডেট করো:

```dotenv
ASSISTANT_CLOUD_ENABLED=true
```

Existing `LLM_PROVIDER` / `LLM_API_KEY` configured থাকলে সেটি server default-এর অগ্রাধিকার পায়।
HF default চাইলে ওই দুই setting খালি রাখবে। Browser-এ নিজস্ব key input তা override করতে পারে।
Gemini/Groq model id বদলাতে server `.env`-এ `GEMINI_MODEL` / `GROQ_MODEL` ব্যবহার করো।
Model retire/access restriction হলে error আসবে; অন্যের অযাচাইকৃত model name ধরে নিও না।

### Terminal 1 — API

```powershell
cd "E:\ETC\FinTech\Working\StudyRoute\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

### Terminal 2 — Next.js UI

```powershell
cd "E:\ETC\FinTech\Working\StudyRoute\web"
npm run dev
```

Browser: http://localhost:3000 । দরকার হলে Ctrl+Shift+R। এই update-এর জন্য backend/runtime
বা web dependencies নতুন করে install লাগবে না; HF model PC-তে download হয় না।

## Gemini/Groq দিয়ে এখনই পরীক্ষা

1. Sign in → Ask the assistant → **AI connection settings** খোলো।
2. Gemini বা Groq নির্বাচন করে provider-এর নিজের API key password input-এ দাও।
3. Context পাঠানো ও encrypted storage-এর consent checkbox পড়ো/টিক দাও → **Test and save connection**।
4. Success হলে পরের প্রশ্ন পাঠাও। আগের conversation থাকবে। Test নিজেও অল্প quota খরচ করতে পারে।
5. `hello`, `ki koro?`, `আমার KYC status কী?`, `how do I fix it?` দিয়ে পরীক্ষা করো।
   Generative model context অনুযায়ী লিখবে; quality model/provider-এর ওপর নির্ভরশীল।
6. Key invalid/blocked হলে activate হবে না। আগের valid connection থাকলে সেটি থাকবে।
   কোনো provider থেকে অন্য paid provider-এ নিজে নিজে switch হবে না।

Key authenticated backend-এ একবার save request-এ যায়; AES-256-GCM encrypted অবস্থায়
নিজের user account-এর setting হিসেবে database-এ থাকে। Browser GET-এ শুধু provider/model/status;
plaintext/ciphertext/key suffix ফেরত আসে না। Chat request-এ key আবার পাঠানো লাগে না।
Refresh, new tab ও logout/login-এ setting থাকে; **Remove saved key** দিয়ে delete করুন।
Quota exhaustion-এর test-এ key save হতে পারে, কিন্তু **unverified** দেখাবে—quota/validity verified নয়।
অন্য invalid/network/unsafe test failure-এ আগের saved setting overwrite হয় না।
HTTPS ব্যবহার করুন, localhost ছাড়া plain HTTP নয়। Shared demo account-এ personal key রাখবেন না:
একই account-এ login করতে পারলে অন্য ব্যক্তি saved key-এর quota ব্যবহার করতে পারবে।
Server encryption secret/DB backup রাখুন। বিস্তারিত: [SAVED_API_KEY.bn.md](SAVED_API_KEY.bn.md)।

## Hugging Face free model চালু করা — একবার করতে হবে

**নিজের account-এ deployment দরকার।** Random public demo-এর API চুরি/বাইপাস করে ব্যবহার নয়।

বর্তমান HF docs অনুযায়ী verified email ও ৩০ দিনের বেশি পুরোনো eligible free account
নিজের ZeroGPU Space host করতে পারে। Free authenticated account-এর included quota বর্তমানে
প্রতিদিন ৫ মিনিট GPU compute; এটি ৫ মিনিট chat duration নয়। Policy/eligibility বদলাতে পারে।
HF Inference Providers আলাদা billing service; free hosting-এর বিকল্প হিসেবে unlimited-free দাবি নয়।

1. Hugging Face-এ নতুন **Gradio Space** বানাও। ZeroGPU hardware select করো।
   Account-এ option না থাকলে free deployment ধরে নেওয়া যাবে না।
2. শুধু `deploy/huggingface-space/`-এর **README.md, app.py, requirements.txt** upload করো।
   StudyRoute `.env`, data, API keys বা পুরো project upload করবে না।
3. Random secret বানাতে PC-তে এই command চালাতে পারো (এটা model download করে না):

```powershell
py -3.13 -c "import secrets; print(secrets.token_urlsafe(32))"
```

4. তৈরি হওয়া secret HF Space **Settings → Variables and secrets**-এ `SPACE_APP_SECRET`
   নামে **secret** হিসেবে রাখো। কোনো screenshot/chat/Git commit-এ secret দিও না।
5. Space Running হওয়া পর্যন্ত অপেক্ষা করো। Model weights HF server-এ download হবে।
6. HF token বানাও, ওই Space access করার minimum প্রয়োজনীয় permission দাও।
   Backend-এর root `.env`-এ নিচের তিনটি value **নিজের machine-এ** বসাও:

```dotenv
HF_SPACE_URL=https://YOUR-DIRECT-SPACE-ORIGIN.hf.space
HF_TOKEN=YOUR_PRIVATE_HF_TOKEN
HF_SPACE_APP_SECRET=THE_SAME_RANDOM_SECRET
```

`YOUR...` text বাস্তব value দিয়ে বদলাবে। `/spaces/owner/name` page URL নয়—Space-এর direct
HTTPS origin লাগবে। Backend restart করো। Provider key remove করে HF path test করো।

Deployment source-এর candidate model: **Qwen/Qwen3-4B-Instruct-2507**, নির্দিষ্ট revision pinned।
এটি resource-conscious multilingual candidate; সব ক্ষেত্রে “best” বা ভুলহীন model দাবি নয়।
HF shared CPU RAM/GPU runtime-এ actual build, cold start, memory ও Bangla quality পরীক্ষা বাকি।
যদি runtime version/model environment না মেলে, আগে Space build logs ঠিক করতে হবে।

## Limit শেষ হলে কী দেখাবে

- HTTP `Retry-After`, Google's structured `RetryInfo`, অথবা পরিচিত ZeroGPU
  `Try again in HH:MM:SS` error পেলে reported deadline থেকে countdown।
- Reset time না জানালে **exact time unavailable**; কোনো বানানো ২৪ ঘণ্টা timer নয়।
- GPU queue full হলে queue message; quota exhausted বলা হবে না। Queue ETA গ্যারান্টি নয়।
- Time শেষ হলে manual retry করা যাবে; availability ফিরে এসেছে এমন গ্যারান্টি নয়।
- তখনই চালাতে চাইলে অন্য Gemini/Groq key input/test করতে পারো। সেখানেও quota আছে।
- HF token installation-wide; এই setup-এর সব StudyRoute user সেই operator quota share করে।

## Privacy / scope

প্রশ্ন, masked app facts এবং bounded recent conversation remote service-এ পাঠানো হয়।
Regex masking সব ধরনের PII সরাতে পারে না। Synthetic data ব্যবহার করবে; real passports,
IDs, bank details বা sensitive documents দেবে না। HF/Gradio/provider-এর নিজস্ব privacy ও
retention policy প্রযোজ্য। Local code prompt log করে না, কিন্তু provider infrastructure-এর
জন্য zero retention দাবি করা হচ্ছে না।

Both Next.js (`web`) and legacy Vite (`frontend`) support cloud controls. Docker compose
এখন নতুন server env forward করে; proxy timeout bounded inference retry-এর জন্য বাড়ানো।
Default cloud mode-এ missing Space/key হলে “not connected” message দেখা expected।
`ASSISTANT_CLOUD_ENABLED=false` কেবল ইচ্ছাকৃত reviewed offline/template mode-এর জন্য।
Legacy Anthropic/OpenAI-compatible paths রাখা আছে; তাদের পূর্বের labelled fallback অপরিবর্তিত।

## Official references

- https://huggingface.co/docs/hub/en/spaces-zerogpu
- https://huggingface.co/docs/inference-providers/en/pricing
- https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
- https://ai.google.dev/gemini-api/docs
- https://console.groq.com/docs/openai
- https://www.gradio.app/guides/querying-gradio-apps-with-curl
