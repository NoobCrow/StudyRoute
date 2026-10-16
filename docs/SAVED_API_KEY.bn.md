# API key refresh/new tab-এ রাখা — cumulative update

## কী ঠিক হয়েছে
- আগের tab-memory-only key এখন optional encrypted backend setting। একবার **Test and save connection**
  করলে refresh/new tab-এ আবার key দিতে হবে না। একই account-এ logout/login করলেও থাকবে।
- Login-এর sessionStorage সমস্যা আগের cookie-session fix-সহ এই ZIP-এ আছে।
- Parent/student-এর saved key আলাদা; household বা delegated AI actor দিয়ে অন্যের key পাওয়া যায় না।
- Browser storage-এ API key রাখা হয়নি। UI-তে শুধু provider/model/status ফিরে আসে; password input খালি থাকে।
- **Remove saved key and use default provider** server-এর saved key delete করে; open tab-গুলো metadata
  refresh করে। Delete fail হলে key remove হয়েছে বলা হয় না। Conversation মুছে যায় না।
- Save-এর synthetic test quota খরচ করতে পারে। 429 হলে key **unverified** হিসেবে save হয়, যাতে পরে
  আবার paste না লাগে। Invalid/network/unsafe response হলে আগের saved key overwrite হয় না।
- Saved provider-এর quota শেষ হলে সেই error-ই দেখাবে; গোপনে HF/template/অন্য paid provider-এ switch নয়।

## Windows-এ install
1. Backend/frontend terminal-এ Ctrl+C। Project-এর backup রাখুন।
2. ZIP extract করে `StudyRoute`-এর **ভিতরের** files/folders আপনার existing
   `E:\ETC\FinTech\Working\StudyRoute`-এ copy/merge/replace করুন। Nested folder নয়।
3. `.env`, `.venv`, `backend/data`, `node_modules` **মুছবেন না**। নতুন dependency লাগে না।
   Existing DB reset/seed/delete করবেন না। Startup additive `saved_ai_connections` table তৈরি করবে।
4. Backend:
   ```powershell
   cd "E:\ETC\FinTech\Working\StudyRoute\backend"
   .\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
   ```
5. অন্য terminal:
   ```powershell
   cd "E:\ETC\FinTech\Working\StudyRoute\web"
   npm run dev
   ```
6. পুরোনো app tab বন্ধ করে `http://localhost:3000` খুলুন, প্রয়োজন হলে login করুন।
   একই exact URL ব্যবহার করুন; localhost ও 127.0.0.1 এক origin নয়।
7. Assistant → **AI connection settings** → provider/key → storage/context consent →
   **Test and save connection**। পুরোনো memory-only key নিজে থেকে migrate হবে না: একবার save করতে হবে।
8. Refresh → assistant খুলুন → saved provider থাকবে। নতুন tab-এও থাকবে। Password field খালি থাকা
   স্বাভাবিক; key browser-এ ফেরত আসে না। Logout/login-এও থাকবে। Remove করলে স্থায়ীভাবে delete হবে।
9. Local persistence fix-এর জন্য HF Space-এ কোনো file upload লাগবে না। Production হলে frontend
   rebuild (`npm run build`), same-origin API proxy/HTTPS/CSP বজায় রাখুন।

## নিরাপত্তা ও সীমাবদ্ধতা
- শুধু নিজের private account/server-এ personal key রাখুন। Shared demo login জানলে অন্য ব্যক্তি
  plaintext দেখতে না পেলেও saved key ব্যবহার করে quota খরচ করতে পারবে।
- AES-256-GCM server-side encryption; এটি end-to-end vault নয়। Server administrator/master-secret
  compromise হলে encryption alone যথেষ্ট নয়। Key কখনো chat/screenshot/Git-এ দেবেন না।
- `DATA_ENCRYPTION_KEY` বা sandbox-এর existing `backend/data/dev_secrets.json` বদলাবেন/মুছবেন না।
  DB ও encryption secret-এর protected backup রাখুন। হারালে পুরোনো key decrypt হবে না; restore করুন
  অথবা Remove saved key দিয়ে মুছে আবার save করুন।
- Save থাকার অর্থ unlimited quota নয়। Gemini/Groq/HF-এর নিজেদের limit অপরিবর্তিত।
- HF test-এর generic system prompt ও app-এর product facts/history/guards আলাদা, তাই উত্তরও আলাদা।
  Model badge একটি model label; সেটি একা live inference-এর প্রমাণ নয়।
- Automated provider calls mocked; live Gemini/Groq/HF inference/quality এই update-এ developer test করেনি।
  Test coverage ও সীমাবদ্ধতা: `SAVED_API_KEY_VALIDATION.json`।
