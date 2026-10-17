# StudyRoute — কী ঠিক করা হয়েছে

## Code ও security hardening
- JSON credential scan, private environment/key file exclusion এবং source-only ZIP packaging ঠিক করা হয়েছে।
- Trained-dialogue mode-এ missing/conflicting তথ্য পরিষ্কার করা ও plan-এর আগে confirmation বাধ্যতামূলক;
  turn limit দিয়ে এই review এড়ানো যায় না। Payment approval এখনও human/MFA-controlled।
- Local SQLite audit anchor-কে external/immutable বলা বন্ধ করা হয়েছে। Coordinated rewrite-এর regression
  এবং আলাদাভাবে সংরক্ষিত checkpoint দিয়ে detection যাচাইয়ের CLI আছে। Independent storage deploy করা হয়নি।
- OUR charge code-কে real-world full receipt-এর guarantee হিসেবে দেখানো হচ্ছে না; accepted university
  payment route যাচাইয়ের warning আছে। Institution-specific route enforcement এখনও নেই।
- Production CSP না কমিয়ে dependency lifecycle patch প্রয়োগ ও browser tests যাচাই করা হয়েছে।
- AI benchmark provenance, পুনর্ব্যবহৃত holdout-এর সীমা, raw RL বনাম runtime review আলাদা করা হয়েছে।

## এই ZIP-এ আছে
সম্পূর্ণ source, model weights, tests, contracts, docs, repaired deck, প্রায় 95 সেকেন্ডের actual local
sandbox demo, subtitles, fresh test/evaluation logs এবং `RELEASE_MANIFEST.sha256`।
`node_modules`, virtual environment, `.git`, `.env`, runtime database ও cache source নয়—ইচ্ছাকৃতভাবে বাদ।

## যাচাই
- Backend: 1542 passed; শেষ financial wording/review regression: 42 passed।
- Frontend: 439 passed; desktop/mobile production-CSP browser tests: 24 passed।
- Production build, TypeScript, ESLint, Prettier ও ruff: passed।
- তিনটি Solidity contract পুনরায় compile করে supplied artifacts-এর সঙ্গে byte-identical পাওয়া গেছে।
- বিস্তারিত ফল ও সীমা: `submission/evidence/release/VERIFICATION.md`।

## আপনার কাজ এখনও বাকি
1. আগে exposed Hugging Face token ও সংশ্লিষ্ট deployed secrets revoke/rotate করুন। পুরোনো encrypted data
   না বুঝে encryption key বা database delete করবেন না। ZIP পরিষ্কার করলেই পুরোনো token revoke হয় না।
2. `GITHUB_PUSH_BN.md` অনুযায়ী backup branch নিয়ে existing fork-এ files overlay করুন; scan, diff, test,
   commit ও PR/push করুন। এখানে GitHub push করা হয়নি।
3. Team attribution/ownership, registration, private-repo judge access ও fresh deployment নিজে নিশ্চিত করুন।
4. Live bank quote/বাস্তব student validation ও independent security review এখনও হয়নি।

**85+/100 নিশ্চিত করা সম্ভব নয়।** Known fixes ও reproducible evidence দেওয়া হয়েছে; বাস্তব validation,
innovation ও official judging-এর বদলে test count বা UI polish-কে score-এর নিশ্চয়তা ধরে নেবেন না।


## v2: আরও যে কাজ হয়েছে
- MMU self-funded tuition-এর official Flywire policy অনুযায়ী backend guard; explicit declaration
  বা নির্দিষ্ট full-name recognition থেকে binding হয়, rename করে এটি সরানো যায় না।
- Quote ছাড়াও draft, approval request, approve, system submit-এ recheck; GET blockers-ও দেখায়।
- Existing SQLite database-এ নতুন table additiveভাবে তৈরি হয়; database reset প্রয়োজন নেই।
- Unknown university identity/route এখনো verified নয়। বানানো নামে declaration বাদ দিলে এই ছোট
  catalogue সব recipient শনাক্ত করতে পারে না। এটি production compliance বা account verification নয়।
- নতুন AI-authored frozen challenge ও security lab evidence: `submission/evidence/v2/`।
  Synthetic test score প্রতিযোগিতার score নয়। নতুন bank quote, user study বা cloud LLM test হয়নি।
