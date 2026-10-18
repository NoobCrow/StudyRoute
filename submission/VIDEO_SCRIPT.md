# Demo video script: three people, one payment

**Target length 4:40. Hard limit 5:00** (the competition rule). English voice-over. Everything on screen is a
**sandbox with synthetic data**; no real money, bank or person is involved.

This page is written for a teammate who has never used StudyRoute. Read it once from top to bottom, do the
preparation in part 2, then record. You do not need to understand the code. You only click what the table says
and read the words in the "Say" column.

## 1. The idea in one minute

StudyRoute helps a family in Bangladesh pay a student's tuition abroad. The video follows **one payment** through
the hands of **three people**:

| Person | What they do in the video | Window |
|--------|---------------------------|--------|
| **Parent** (pays from Dhaka) | Compares providers, asks the assistant in one sentence, sees the AI risk score, approves with an MFA code | **A** |
| **Bank reviewer** (admin) | A person at the sandbox bank looks at a payment the AI marked unusual, and clears it with an MFA code. Then verifies the audit log | **C** |
| **Student** (abroad) | Sees the same household and payment, but cannot approve. Prepares documents and uses the student guide | **B** |

The message to leave with the judges: **the engine calculates, the AI explains, a human approves, and every step
is logged.**

## 2. Before you record (off camera, about 20 minutes)

### 2.1 What you need
* A laptop with **Google Chrome** and **Microsoft Edge** (or any second browser).
* A microphone (a headset is fine) and a quiet room.
* A screen recorder. Easiest: **OBS Studio** (free, obsproject.com). In OBS: Sources, **+**, **Display Capture**;
  check that **Mic/Auxiliary** shows moving green bars when you talk; **Settings, Output** keep the default;
  **Start Recording** / **Stop Recording**. The file lands in your Videos folder. (The Windows Snipping Tool,
  Win+Shift+R, also works if it records your microphone.)
* About 2 GB free disk space.

### 2.2 The three accounts (all synthetic; the password and code are public demo values)
| Role | Window | Browser | Email | Password |
|------|--------|---------|-------|----------|
| Parent | A | Chrome, normal window | `parent@demo.studyroute.test` | `Sandbox#2026` |
| Student | B | Chrome, **Incognito** window (Ctrl+Shift+N) | `student@demo.studyroute.test` | `Sandbox#2026` |
| Reviewer (admin) | C | **Edge** | `admin@demo.studyroute.test` | `Sandbox#2026` |

**MFA code for every confirmation box: `246810`.**
Website: **https://studyroute.bot-keep.xyz** (the same app also runs locally with `docker compose up --build` at
http://localhost:8080; the steps are identical).

### 2.3 Sign in to all three windows first (so no sign-in appears on camera)
1. Open the three windows, maximise each, and sign in as above. **Wait 10 seconds between sign-ins**: the sandbox
   allows only about ten sign-in attempts a minute. If you see "too many requests", wait one minute.
2. Browser zoom 100% (Ctrl+0). Hide the bookmarks bar (Ctrl+Shift+B). Close every other tab and program.
3. Turn on Windows **Do not disturb** so no notification pops up.
4. You will switch windows with **Alt+Tab**. Practise once: A, B, C, A.

### 2.4 Stage the payment the bank will look at (ask Farhan, one command)
The reviewer scene needs one payment that the AI has marked unusual. A script makes it in a few seconds.
**Farhan runs this in PowerShell** (on the computer that has the project):

```powershell
cd I:\FINTECH\backend
.\.venv\Scripts\python.exe -m app.scripts.review_demo --base-url https://studyroute.bot-keep.xyz --leave-open
```

* It prints lines starting with `OK`; the last line is `Left waiting for the bank: pay_...`. That is the payment.
* If it prints `429` or "too many requests", wait one minute and run it again.
* If it prints `FAIL`, stop and tell Farhan; do not record.
* **Run it again right before every recording attempt of Take 2** (see 2.5): a payment's price quote is valid for
  only five minutes, and an old staged payment will ask for a fresh quote.

### 2.5 Record in two takes, then join them
Why two takes: the staged payment's quote expires after five minutes, so everything that touches it must be filmed
within about three minutes of the staging command.

* **Take 1 (scenes 0 to 3, about 1:30):** can be recorded any time. Parent compares and uses the assistant.
* **Take 2 (scenes 4 to 9, about 3:10):** stage the payment (2.4), wait for `Left waiting for the bank`, then
  press Record within one minute and go straight through.

Join the two clips: open **Clipchamp** (built into Windows 11), **Create a new video**, drag Take 1 and Take 2
onto the timeline in that order, **Export, 1080p**. (Any editor works. If you cannot join them, tell Farhan and
send both clips.)

### 2.6 Do a dry run
Do the whole thing once without recording, with a timer. Then record. A calm, slightly slow voice beats a fast
one. If you make a mistake, **stop talking, pause three seconds, and say the sentence again**; the pause is easy
to cut.

## 3. Take 1: the parent (record in window A)

| Time | Scene | What to do (clicks) | Say (read these words) |
|------|-------|---------------------|------------------------|
| 0:00 | **0. Introduction** | Show the sign-in page or the dashboard in window A. Keep the amber banner "Sandbox. Synthetic data, no real money moves" visible | "Last year Bangladeshi families sent 881.7 million dollars through banks for overseas education. Paying tuition abroad is slow, costly and risky. This is StudyRoute, a sandbox where nothing is real. I will follow one payment through three people: the parent, the bank and the student." |
| 0:20 | **1. Parent: dashboard** | Window A, **Dashboard**. Point the mouse at the **Deadline planner** (due date 1 Nov, latest send date) | "I am the parent, in Dhaka. The planner works backwards from the due date to my latest send date." |
| 0:30 | **2. Parent: compare** | Click **Compare** in the left menu. Leave the defaults (United Kingdom, GBP 10,000, tuition). Click **Get quotes**. Wait two seconds. Scroll slowly to the **Quotes** table; point at Provider C's red "Short by GBP 35". Scroll down to **Currency-drop stress test** | "Compare ranks providers by true total cost, including the hidden exchange-rate margin. Provider B is cheapest at 1.58 percent. Provider C looks close but would leave the university 35 pounds short, so the screen warns me. The stress test shows my cost if the taka weakens." |
| 1:00 | **3. Parent: the assistant** | Click **Ask the assistant** (top right). Type: `I need to pay GBP 10,000 tuition to a UK university by 1 November` and press Enter. When the card "Before I plan your payment, please check what I understood" appears, pause **three seconds**, then click **Yes, plan it**. Show the plan card. Close the chat with the X | "I can also type one sentence. A small trained model reads it, but before planning it must read back what it understood, and I confirm. Every number comes from the engine, never the AI, and the assistant says it cannot approve, submit or cancel." |

**Stop Take 1 here (about 1:30).** Do not click anything that creates a payment.

## 4. Take 2: the payment, the bank, the student (stage first, then record)

Start recording only after the command in 2.4 has printed `Left waiting for the bank`. Be in window A.

| Time | Scene | What to do (clicks) | Say (read these words) |
|------|-------|---------------------|------------------------|
| 1:30 | **4. Parent: the AI risk score** | Window A. Click **Payments**. Open the newest payment, **GBP 8,000** to "Visiting University ... (synthetic)", state **Waiting for the bank**. Scroll to the card **"The bank's check"**: read the number "AI risk score N out of 100", the **medium risk** label and the four factors (Amount, Frequency, Timeline, Person) | "Here is a larger payment to a university I have never paid. The AI gives it a risk score out of a hundred from four factors: amount, frequency, timeline and person. Medium means a warning, and a person at the bank looks. The score never approves; I still need my own MFA code." |
| 2:00 | **5. Reviewer: the bank's decision** | **Alt+Tab to window C (Edge, admin).** Click **Bank review** in the left menu. The queue shows one waiting payment: open it (if there are older ones, open the one whose reference matches the payment you just saw). Scroll the **Bank review brief**: facts, AI risk score, reasons, the hint. Choose **Yes, clear it**, click **Sign with MFA and send**, type `246810`, confirm | "Now I am the reviewer at the sandbox bank. Most payments never reach this desk. This one did. The brief shows the facts, the AI's reading and what to check. The AI cannot clear, decline or approve: I decide, and I sign my answer with a fresh MFA code." |
| 2:40 | **6. Parent: approve** | **Alt+Tab to window A.** Reload the payment page (F5). Click **Approve with MFA**, confirm the summary, type `246810`, confirm. Show the **Status tracker** moving to SETTLED (wait up to ten seconds; if it is still on "Submitted", press F5 once) | "Back as the parent. Approval is mine alone: I confirm the summary I saw, with a fresh MFA code bound to this payment. The simulated provider settles it by a signed webhook, and the tracker shows each step." |
| 3:10 | **7. Student** | **Alt+Tab to window B (Incognito, student).** Press F5 on the **Dashboard** and point at "Household of Demo Parent. As the student you can look and prepare, but only the paying parent can approve". Click **Payments**, open the same payment and point at "Only the paying parent can request approval and approve". Click **Documents** (the checklist, 0 of 9 ready). Click **Student guide**: type `130000` in Monthly budget, point at the cities that fit, click **Details** on one city, then click the **Arrival checklist** tab and scroll it | "Now the student, abroad. She sees the same household and payment and can follow its status, but there is no approve button: only the paying parent can approve. She can prepare: the document checklist the bank may ask for, and the student guide. She types a monthly budget and it lists the cities that fit, with rent and total cost, and an arrival checklist for her first weeks." |
| 3:55 | **8. Reviewer: the audit log** | **Alt+Tab to window C.** Click **Audit log**, then **Verify the hash chain**. The green box "Chain verified: PASS" appears. Point at the newest rows (the clearance, the approval) | "Everything each person did is in an audit log where every event holds the hash of the one before. One click recomputes the chain: pass. In our tests, editing a single row makes it fail at that event." |
| 4:20 | **9. Close** | Stay on the audit page, or show the sign-in page | "This is a sandbox: rates, fees and banks are invented, and no real parent or bank has tried it. What is real is the design: the engine calculates, the AI explains, a human approves, every step is logged. StudyRoute: clear, cheap and safe." |

**End of Take 2 at about 4:40.** Stop recording.

## 5. If something goes wrong
| Problem | What to do |
|---------|------------|
| The risk card says **Low** or "No warning" | Say instead: "A low score shows no warning and the payment takes the fast lane: nobody waits." Then skip scene 5's clearance and say "The reviewer's desk is empty when nothing is unusual." Better: re-stage (2.4) and try again |
| The payment says **"This payment needs a fresh quote"** | The quote expired (five minutes). Run the staging command again and redo Take 2 |
| A sign-in says "too many requests" | Wait one minute. You should not need to sign in during a take |
| Window C shows several waiting payments | Open the newest one (or the one named in the command's last line) |
| **Approve with MFA** is missing | The bank has not cleared it yet (go back to scene 5), or you are in the wrong window |
| The tracker is not at SETTLED | Press F5 once; if still not, say "the simulated provider settles it moments later" and continue |
| You are over 5:00 | Drop scene 1, shorten scene 2 (skip the stress test), and keep the rest. Never cut the risk score, the reviewer or the student: they are the point |
| You are under 4:00 | Add **Bank network** (the three hops) or **Smart escrow** for ten seconds each, and say "also simulated" |

## 6. Words to avoid (the rules)
* Never say a payment is **"legal"**, **"within the limit"**, **"safe from fraud"** or **"guaranteed"**. If you
  must say something, use: **"Indicative. Confirm with your AD bank."**
* Never say it connects to a real bank, a live exchange-rate feed or real people. Say **"sandbox"** and
  **"synthetic"**.
* Say **"the AI scores or explains; a person decides"**. Never say the AI approves, clears or decides.
* Do not read out numbers on screen faster than the screen shows them; read the number you see (the risk score
  will be around 99).
* Do not show a browser's saved passwords or any real account, and do not type real data.

## 7. After recording
1. Watch the whole video once. Check: the voice is clear, the sandbox banner is visible, **no sign-in screen
   appears in the middle**, and the total is **under 5:00** (look at the file's length in Windows Explorer).
2. Name the file `StudyRoute_Demo_Video.mp4`.
3. Put it in `FINAL_SUBMISSION\03_Demo_Video\` (next to `PUT_THE_VIDEO_HERE.txt`) **and** upload it for the e-mail:
   YouTube **Unlisted**, or Google Drive "Anyone with the link can view". Open the link in a private window to be
   sure it plays.
4. Send Farhan the link and the file. The e-mail text has a line for the video link.
5. Optional: add English subtitles. The words in the "Say" column are the subtitles.

## 8. Other material
`StudyRoute_Demo.mp4` in this folder is an older, silent screen recording of the local app (with subtitles). It is
supporting material only; the narrated video above is the one to submit. The steps are rehearsed by
`python -m app.scripts.demo_flow` (the longer 14-step flow) and `python -m app.scripts.review_demo` (the bank
review you staged in 2.4).
