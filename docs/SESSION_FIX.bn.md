# StudyRoute — cumulative assistant + multi-tab session update

## কী বদলেছে
- নতুন tab/reload-এ একই browser profile ও একই exact origin-এর login পুনরুদ্ধার হয়।
- Auth refresh credential আর sessionStorage/localStorage-এ রাখা হয় না। পুরোনো `sr.refresh`
  entry শুধু মুছে যায়; অন্য preferences মুছে না। আপডেটের পরে একবার নতুন করে login করুন।
- Server-এ hashed opaque browser session; cookie HttpOnly, SameSite=Strict, host-only,
  path `/api/v1`, production-এ Secure। Access JWT memory-only এবং cookie/session-এর সঙ্গে bound।
- Restore-এর আলাদা ৬০/minute/IP budget; login-এর ১০/minute/IP brute-force limit অপরিবর্তিত।
  স্বাভাবিক tab switching login budget খরচ করে না; logout-এরও আলাদা budget।
- Default absolute lifetime পূর্বের `REFRESH_TOKEN_TTL_SECONDS` (৭ দিন)। Restore করলে মেয়াদ বাড়ে না।
  Session cookie প্রতি restore-এ rotate হয় না: concurrent tab replay-race এড়ানোর জন্য stable opaque
  server session। Login-এ নতুন session, আগের cookie session revoke; logout-এ server revoke।
  পুরোনো `/auth/login`, `/auth/refresh`, `/auth/logout` bearer API-এর one-use rotation অপরিবর্তিত।
- Exact Origin + `X-StudyRoute-Browser: 1` required; cross-site/null/missing Origin rejected।
  HttpOnly একা CSRF/XSS protection নয়। CORS credentials বন্ধই আছে; browser same-origin proxy ব্যবহার করে।
- BroadcastChannel-এ শুধু `auth-changed` event, কোনো token/key/user data নয়। Focus/visibility-তেও restore।
- Account বদলালে account UI/chat unmount এবং Next query cache নতুন হয়। Gemini/Groq key tab-memory-only;
  অন্য tab-এ share নয়, logout/account change-এ মুছে যায়।
- Logout request fail হলে “logout হয়েছে” বলা হয় না; connection ঠিক করে retry করতে হবে।
- পুরোনো async restore নতুন login/logout-এর token overwrite করতে পারে না। Invalid MFA response-এ
  অপ্রয়োজনীয় session restore দিয়ে আসল error ঢেকে দেওয়া হয় না।

## Assistant-এর উত্তর কেন আলাদা ছিল
HF Space test-এ সাধারণ helpful-assistant prompt; app-এ product scope, current facts, history ও guards।
একই model হলেও inputs আলাদা, তাই ভাষা/উত্তর আলাদা হওয়া স্বাভাবিক। কিন্তু identity-তে KYC টেনে আনা,
ভুল service বলা বা mock documents দিলেই payment approval হবে বলা ঠিক নয়। এই update-এ product
knowledge/relevance/targeted claim guards এবং Banglish identity routing যুক্ত আছে।
`ke apni?` আর `তুমি কীভাবে আমাকে সাহায্য করতে পারো?` explicit general-help প্রশ্ন।
`3+5=??`-এর মতো bounded binary arithmetic server-side Decimal calculator-এ হিসাব হয়ে FACT হিসেবে
model-এ যায়; eval/code execution নয়। এটি general maths engine নয়: দুইটি ছোট সংখ্যা, + - * /,
non-terminating division/zero division/financial instructions প্রত্যাখ্যান করে। Financial quote/FX/fees
সবসময় আগের payment engine থেকে আসে; model নিজের মতো অঙ্ক করতে পারে না।

Model-এর সব hallucination দূর হয়েছে এমন দাবি নয়। Regression model HTTP mocked; নিজের HF/Gemini/Groq
account দিয়ে live quality test আলাদা করতে হবে। Provider rate limit হলে reported সময় থাকলেই countdown;
না থাকলে unknown। Managed cloud error হলে silent template/provider fallback করা হয় না।

## Windows-এ বসানো (আগের project মুছবেন না)
1. Backend/frontend terminal-এ Ctrl+C দিন। Current project-এর backup রাখুন।
2. ZIP extract করলে `StudyRoute` folder-এর **ভিতরের** files/folders current
   `E:\ETC\FinTech\Working\StudyRoute`-এ copy/merge/replace করুন। Nested StudyRoute বানাবেন না।
3. `.env`, `.venv`, `backend/data`, `node_modules` মুছবেন না। ZIP-এ এগুলো নেই। নতুন dependency নেই।
4. HF Space-এ auth fix upload লাগবে না; local backend ও frontend দুটোই update করতে হবে।
5. Backend terminal:
   ```powershell
   cd "E:\ETC\FinTech\Working\StudyRoute\backend"
   .\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
   ```
   Startup-এ additive `browser_sessions` table তৈরি হয়; existing DB reset/seed/delete করবেন না।
6. আরেক terminal:
   ```powershell
   cd "E:\ETC\FinTech\Working\StudyRoute\web"
   npm run dev
   ```
7. সব পুরোনো app tab বন্ধ করে `http://localhost:3000` খুলুন এবং একবার login করুন।
   তারপর নতুন tab-এ **একই URL** খুলুন। localhost ও 127.0.0.1 আলাদা cookie origin; mixed URL নয়।
8. এক tab-এ logout করলে অন্য tab-ও sign out হবে। Expiry, incognito, অন্য browser/profile, cookie
   clear/block করলে login আবার লাগবে—এটাই সঠিক। Default provider config `.env` অপরিবর্তিত রাখুন।
9. API key chat বা screenshot-এ দেবেন না। App-এর private API-key input-এ দিন।

## Production ও proxy
HTTPS required (Secure cookie)। Frontend ও API same-origin nginx/Next proxy দিয়ে serve করতে হবে;
`/api/v1` path/Set-Cookie/Origin preserve করুন। অন্য dev port/custom deployment হলে exact trusted
`CORS_ORIGINS` configure করুন, wildcard নয়। Frontend build পুনরায় করুন (`npm run build`) যাতে
নতুন hashed CSP bootstrap policy তৈরি হয়। Browser-native passkey/security settings bypass নয়।

## নিজে acceptance test
- Parent login -> new tab -> same account; একসঙ্গে দুই tab reload -> দুটোই signed in।
- এক tab logout -> অন্য tab signed out; reload করলেও signed out।
- Student login -> আগের Parent chat/key/quote দেখা যাবে না।
- পরিচয়, app overview, KYC status আলাদা প্রশ্ন করুন; relevance আলাদা হওয়া উচিত।
- HF test আর app reply শব্দে শব্দে মিলবে না; app-এর তথ্য সঠিক ও প্রশ্নসংশ্লিষ্ট কি না দেখুন।
- Incognito/extension-off-এ hydration warning যাচাই করুন। Screenshot-এর `wotdisconnected`
  injected attribute extension হতে পারে, কিন্তু warning hide করতে suppressHydrationWarning যোগ হয়নি।
