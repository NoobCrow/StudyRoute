# StudyRoute assistant quality update

## Product grounding সংশোধন (v2)
Account facts সরানোর পর overview উত্তরে model ভুল product description বানাচ্ছিল। এখন
system instructions-এ reviewed app features ও বাংলা terminology দেওয়া হয়েছে। Admission,
competition, scholarship বা promise-checking platform হিসেবে বর্ণনা না করার নির্দেশ আছে।
এটি model-কে দেওয়া factual background, এক প্রশ্নের fixed reply নয়। এই prompt পরিবর্তনে
সব hallucination নির্মূলের নিশ্চয়তা নেই। Final focused suite: 209 passed, lint clean;
এই v2 দিয়ে live remote inference এখনও developer দ্বারা পরীক্ষা করা হয়নি।

## কী বদলেছে
- Cloud conversation-এর সাধারণ পরিচিতি/greeting/app-help প্রশ্নে current KYC, caps,
  bank-reference figures বা document excerpts আর পাঠানো হয় না। KYC/limits/deadline/checklist
  প্রশ্নে সংশ্লিষ্ট fact subset যায়; fact ID অপরিবর্তিত থাকে। Financial task engine অপরিবর্তিত।
- Screenshot-এর বাংলা overview প্রশ্নটি app-overview route-এ নেওয়া হয়। এটি উত্তর hardcode
  করে না: cloud mode-এ model-ই প্রাসঙ্গিক উত্তর লেখে।
- English/Bangla/কিছু Banglish future approval/sending guarantees এবং বাংলা action claim-এর
  targeted output checks যোগ হয়েছে। Known unsupported account statuses reject করা হয়।
- Cap উল্লেখ করা প্রতিটি বাক্যে sandbox এবং not-legal/bank-limit qualifier দরকার। Cap-এর
  engine number ব্যবহার করলেও এই check হয়। সংখ্যামাত্র মিলে গেলে দাবি নিরাপদ ধরে নেওয়া হয় না।
- Unsafe output retry হয়; দ্বিতীয়বারও ব্যর্থ হলে explicit unsafe-response message আসে।
  Silently hardcoded success answer দেওয়া হয় না।
- Space requirements-এ transformers==5.0.0 রাখা হয়েছে (তোমার Space-এ ইতিমধ্যে বদলানো)।

## গুরুত্বপূর্ণ সীমাবদ্ধতা
এই regex-based checks সাধারণ semantic সত্যতা যাচাই করতে পারে না। সব ভাষা, paraphrase,
negation বা ভুল দাবি ধরার নিশ্চয়তা নেই; conservative checks সঠিক উত্তরও reject করতে পারে।
LLM model এখনও ভুল করতে পারে। Human payment approval/authorization backend-এ আলাদাভাবে
বাধ্যতামূলক থাকে। এই update কোনো real-money transfer অনুমোদন করে না।

## বসানোর নিয়ম (বর্তমান cloud update-এর ওপর)
1. VS Code-এ backend চলা terminal-এ Ctrl+C চাপো।
2. ZIP extract করে ভেতরের StudyRoute folder খুলে তার contents নিজের project root-এ merge করো।
   শুধু নতুন/পরিবর্তিত source files replace হবে; পুরো project মুছবে না।
3. .env/.venv/backend/data/node_modules অক্ষত রাখো। API keys বা HF secret বদলাবে না।
4. Backend আবার চালাও:

```powershell
cd "E:\ETC\FinTech\Working\StudyRoute\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

5. web server চালু রাখো; browser refresh করে assistant test করো। নতুন npm/pip install,
   seed বা Hugging Face rebuild প্রয়োজন নেই। ZIP-এর deploy requirements ভবিষ্যৎ redeploy-এর জন্য।

## নিজের app-এ manual test
- Who are you? → পরিচিতি; অপ্রয়োজনীয় নিজের KYC/caps নয়।
- StudyRoute কীভাবে আমাকে সাহায্য করতে পারে? সহজ বাংলায় বোঝাও। → overview।
- What is my KYC status? → current mock status, যদি পাওয়া যায়।
- Does adding mock documents guarantee payment approval? → না; অন্য checks/human approval প্রয়োজন।
- What are the sandbox transaction limits? → sandbox settings, legal/bank limits নয়।
- একই প্রশ্নের একই উত্তর আসা hardcode হওয়ার প্রমাণ নয়: deterministic generation-এ তা হতে পারে।

## Browser error ও login
- wotdisconnected attribute-সহ hydration warning extension injection হতে পারে। Extensions
  ছাড়া Incognito window-এ পরীক্ষা করো। এই patch warning suppress করে না; কারণ যাচাই বাকি।
- ঐতিহাসিক v1/v2 সীমা: তখন login refresh token sessionStorage-এ ছিল; এই cumulative update-এ
  SESSION_FIX.bn.md অনুযায়ী HttpOnly browser session যোগ হয়েছে। আগের standalone quality patch auth
  migration নয়। Secure multi-tab session-এর জন্য HttpOnly cookie, CSRF/origin handling,
  refresh rotation/concurrency ও logout tests-সহ আলাদা কাজ দরকার। localStorage-এ token সরানো হয়নি।
- আগের tab-memory-only key আচরণ এখন superseded: [encrypted saved API key update](SAVED_API_KEY.bn.md)।
  Browser-এ key ফেরত আসে না; একই user-এর সব tab backend setting ব্যবহার করে।

## কী যাচাই হয়েছে
Automated tests স্থানীয় sandbox-এ; cloud HTTP responses mocked। এই patch দিয়ে real HF/Groq/
Gemini request নিজে চালানো হয়নি। আগের user screenshot-এ HF inference সফল ছিল; সেটি নতুন
patch-এর end-to-end verification নয়। UI কোনো change নেই, auth আচরণ অপরিবর্তিত।
