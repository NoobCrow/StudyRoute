"use strict";
// Builds submission/StudyRoute_Deck.pptx (the 10-minute final presentation).
//
//   cd submission/deck && npm install && node build_deck.js
//   node build_deck.js --preview <folder>     also writes <folder>/preview.html for a visual check
//
// Slides are described once as a plain layout model. One renderer turns it into the .pptx
// (theme, layouts, placeholders, sections, speaker notes); another turns the same model into
// absolutely positioned HTML, so every slide can be looked at in a browser without PowerPoint.
// Numbers on the slides are read from the generated docs, so they cannot drift from the repo.
// Everything shown is synthetic: StudyRoute is a sandbox and no real money moves.


// Team name and repository link are set when the deck is built, never hard-coded:
//   TEAM_NAME="..." REPO_LINK="https://github.com/..." node build_deck.js
const TEAM = process.env.TEAM_NAME || "[Team name]";
const REPO = process.env.REPO_LINK || "[repository link]";

const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..", "..");
const OUT = path.join(ROOT, "submission", "StudyRoute_Deck.pptx");
const SHOTS = path.join(ROOT, "submission", "screenshots");

// ---------------------------------------------------------------------------------------------
// Theme: navy for trust, teal from the app, amber for the sandbox banner, red for shortfall.
// ---------------------------------------------------------------------------------------------
const THEME = {
  name: "StudyRoute",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0B2545", lt1: "FFFFFF", dk2: "4A5C70", lt2: "EEF3F8",
    accent1: "0B7A70", accent2: "F4B942", accent3: "C8344A", accent4: "2F6DA3",
    accent5: "C9D6E3", accent6: "2E7D32", hlink: "0B7A70", folHlink: "4A5C70",
  },
};
const SCHEME_TO_SLOT = {
  text1: "dk1", background1: "lt1", text2: "dk2", background2: "lt2",
  accent1: "accent1", accent2: "accent2", accent3: "accent3", accent4: "accent4",
  accent5: "accent5", accent6: "accent6",
};
const hexOf = (token) => THEME.colors[SCHEME_TO_SLOT[token]];

// ---------------------------------------------------------------------------------------------
// Facts the deck quotes, read from the repository.
// ---------------------------------------------------------------------------------------------
function read(relative) {
  return fs.readFileSync(path.join(ROOT, relative), "utf8").replace(/\r\n/g, "\n");
}
function facts() {
  const cases = read("docs/TEST_CASES.md");
  const grab = (re, what) => {
    const m = re.exec(cases);
    if (!m) throw new Error(`docs/TEST_CASES.md has no "${what}". Run python scripts/gen_test_cases.py.`);
    return Number(m[1]);
  };
  const assessment = read("docs/SECURITY_SELF_ASSESSMENT.md");
  return {
    backendTests: grab(/Backend: \*\*(\d+) tests\*\*/, "backend count"),
    frontendTests: grab(/Frontend: \*\*(\d+) tests\*\*/, "frontend count"),
    scenarios: (cases.match(/^\| T\d\d \|/gm) || []).length,
    risks: (assessment.match(/^\| R\d+ \|/gm) || []).length,
  };
}
const AI = JSON.parse(read("submission/evidence/ai_evaluation.json"));
const RL = JSON.parse(read("submission/evidence/ai_rl_evaluation.json"));
const EXPL = JSON.parse(read("submission/evidence/ai_explainer_evaluation.json"));
const RISK = JSON.parse(read("submission/evidence/ai_risk_operating_points.json"));
const F = facts();
if (F.scenarios !== 24) throw new Error(`Expected 24 blueprint scenarios, found ${F.scenarios}.`);

// ---------------------------------------------------------------------------------------------
// Layouts (frames). Titles are placeholders carried by the layout.
// ---------------------------------------------------------------------------------------------
const LAYOUTS = {
  title: { bg: "text1", titleBox: { x: 0.6, y: 1.05, w: 5.8, h: 1.15 }, titleSize: 60, titleColor: "background1" },
  content: { bg: "background1", titleBox: { x: 0.5, y: 0.3, w: 9, h: 0.85 }, titleSize: 36, titleColor: "text1" },
  closing: { bg: "text1", titleBox: { x: 0.5, y: 0.3, w: 9, h: 0.85 }, titleSize: 36, titleColor: "background1" },
};

// ---------------------------------------------------------------------------------------------
// Model helpers. Colours are scheme tokens (text1, accent1, ...); sizes are inches and points.
// ---------------------------------------------------------------------------------------------
const rect = (x, y, w, h, fill, extra = {}) => ({ type: "rect", x, y, w, h, fill, ...extra });
const oval = (x, y, w, h, fill, extra = {}) => ({ type: "oval", x, y, w, h, fill, ...extra });
const text = (x, y, w, h, runs, extra = {}) => ({
  type: "text", x, y, w, h, runs: typeof runs === "string" ? [{ text: runs }] : runs, ...extra,
});
const image = (file, x, y, w, h, alt) => ({ type: "image", file: path.join(SHOTS, file), x, y, w, h, alt });
const card = (x, y, w, h, extra = {}) => rect(x, y, w, h, "background2", { round: 0.08, ...extra });
const shot = (file, x, y, w, h, alt) => [
  rect(x - 0.08, y - 0.08, w + 0.16, h + 0.16, "background1", { round: 0.06, line: "accent5", shadow: true }),
  image(file, x, y, w, h, alt),
];

const slides = [];

// 1 ---------------------------------------------------------------------------------------------
slides.push({
  layout: "title", section: "Opening", title: "StudyRoute",
  notes:
    "Good morning. We are team " + TEAM + ", and this is StudyRoute, our entry for Topic C, the cross-border and student finance assistant. " +
    "StudyRoute is a sandbox AI agent that helps a parent in Bangladesh pay a student's tuition abroad. Everything you will see is synthetic and no real money moves. " +
    "Our design rule is on the slide, and the rest of the talk shows how we make each of those four sentences true and testable: the engine calculates, the AI explains, the human approves, and every step is logged.",
  elements: [
    text(0.6, 0.55, 6.0, 0.3, "TOPIC C  ·  CROSS-BORDER AND STUDENT FINANCE ASSISTANT", { size: 12, bold: true, color: "accent2" }),
    text(0.6, 2.35, 5.7, 1.3,
      "An AI agent that helps a parent in Bangladesh pay tuition abroad: clear costs, safe approval, full audit.",
      { size: 20, color: "background2" }),
    text(0.6, 3.85, 5.7, 1.0,
      "The engine calculates. The AI explains. The human approves. Every step is logged.",
      { size: 16, italic: true, color: "accent2" }),
    text(0.6, 5.0, 5.8, 0.3, `${TEAM}  ·  Sandbox: synthetic data, no real money moves`, { size: 12, color: "accent5" }),
    ...shot("02-compare.png", 6.8, 0.6, 2.8, 2.19, "StudyRoute compare screen ranking three providers"),
    ...shot("12-audit-verify-pass.png", 6.8, 3.05, 2.8, 2.19, "Audit log with the hash chain verified"),
  ],
});

// 2 ---------------------------------------------------------------------------------------------
const pains = [
  ["Hidden margin.", " The rate sits above mid-market, and banks show a fee, not the margin."],
  ["Fees on the way.", " Correspondent and receiving banks deduct from the amount."],
  ["Short payment.", " The university gets less than invoiced and may add a late fee."],
  ["Missed deadlines.", " Two calendars: Friday and Saturday off in Bangladesh, plus the host country."],
  ["Paperwork.", " An unclear document list and weeks of back and forth."],
];
slides.push({
  layout: "content", section: "Opening", title: "The posted fee is not the price",
  notes:
    "A parent in Bangladesh paying tuition abroad usually compares banks by the fee they are shown. But in our synthetic worked example, for GBP 10,000 with Provider B, " +
    "63 percent of the real cost is the hidden exchange-rate margin, not the visible fees. On top of that, correspondent and receiving banks can deduct fees on the way, " +
    "so the university may be paid short, and the deadline has to respect two calendars. Then there is the paperwork. These five problems are what StudyRoute is built around.",
  elements: [
    card(0.5, 1.35, 3.3, 3.75),
    text(0.7, 1.5, 2.9, 1.2, "63%", { size: 66, bold: true, font: "+mj-lt", color: "accent1", valign: "middle" }),
    text(0.7, 2.8, 2.9, 1.1, "of the real cost is the hidden exchange-rate margin", { size: 16, bold: true, color: "text1" }),
    text(0.7, 4.4, 2.9, 0.55, "Provider B, GBP 10,000. Synthetic rates and fees.", { size: 11, color: "text2" }),
    ...pains.flatMap(([lead, rest], i) => {
      const y = 1.35 + i * 0.76;
      return [
        oval(4.1, y + 0.05, 0.36, 0.36, "accent1"),
        text(4.1, y + 0.05, 0.36, 0.36, String(i + 1), { size: 14, bold: true, color: "background1", align: "center", valign: "middle" }),
        text(4.65, y, 4.85, 0.72, [
          { text: lead, bold: true, color: "text1" },
          { text: rest, color: "text2" },
        ], { size: 14, valign: "middle" }),
      ];
    }),
  ],
});

// 3 ---------------------------------------------------------------------------------------------
const people = [
  { x: 0.5, letter: "P", fill: "accent4", head: "The parent in Bangladesh", sub: "Pays in BDT and carries the risk",
    items: ["Compares banks by the posted fee only", "Approves a large transfer with little to check it against", "Must prove source of funds and gather documents"] },
  { x: 5.1, letter: "S", fill: "accent1", head: "The student abroad", sub: "Needs the university paid on time",
    items: ["Tuition arrives short or cannot be matched", "Late fees, or a payment the university cannot match", "Weeks of waiting with no status"] },
];
slides.push({
  layout: "content", section: "The problem", title: "A family carries the risk",
  notes:
    "Two people feel this. The parent pays in taka, compares banks by the posted fee, approves a large transfer with little to check it against, and has to prove where the money came from. " +
    "The student needs the university paid on time: if tuition arrives short or cannot be matched to the invoice, there are late fees and weeks of waiting with no status. " +
    "StudyRoute gives both one plan. The parent decides. The student can see the plan, add recipient details and follow the status, but cannot approve.",
  elements: [
    ...people.flatMap((p) => [
      card(p.x, 1.35, 4.4, 3.2),
      oval(p.x + 0.2, 1.55, 0.5, 0.5, p.fill),
      text(p.x + 0.2, 1.55, 0.5, 0.5, p.letter, { size: 18, bold: true, color: "background1", align: "center", valign: "middle" }),
      text(p.x + 0.85, 1.5, 3.4, 0.6, p.head, { size: 18, bold: true, color: "text1", valign: "middle" }),
      text(p.x + 0.2, 2.2, 4.0, 0.4, p.sub, { size: 14, italic: true, color: "text2" }),
      text(p.x + 0.2, 2.7, 4.0, 1.75,
        p.items.map((t, i) => ({ text: t, bullet: true, breakLine: i < p.items.length - 1 })),
        { size: 14, color: "text1", paraAfter: 6 }),
    ]),
    text(0.5, 4.75, 9, 0.45, "StudyRoute gives both one plan: the parent decides, the student can see.",
      { size: 16, bold: true, color: "accent1", valign: "middle" }),
  ],
});

// 4 ---------------------------------------------------------------------------------------------
const chain = [
  ["Parent", "pays BDT", "text1", "Missing document"],
  ["AD bank", "sells FX, sends SWIFT message", "text1", "Wrong BIC: payment bounces"],
  ["Correspondent bank", "may deduct a lifting fee", "text1", "Fee deducted: tuition short"],
  ["Receiving bank", "credits, may deduct a fee", "text1", "Hold or receiving fee"],
  ["University", "matches by reference", "accent1", "No reference: unmatched"],
];
slides.push({
  layout: "content", section: "The problem", title: "How money really moves",
  notes:
    "This is the real chain. The parent pays in taka to an authorised dealer bank, which sells foreign currency and sends a SWIFT instruction carrying a UETR and a charge code. " +
    "A correspondent bank may take a lifting fee, the receiving bank may take another, and the university matches the payment by reference. Each step has a typical failure, shown in red. " +
    "StudyRoute simulates this chain end to end with invented banks, a correspondent and a double-entry ledger where debits equal credits, and a failed payment is returned in full. It never moves real money.",
  elements: [
    ...chain.flatMap(([head, sub, fill, risk], i) => {
      const x = 0.5 + i * 1.84;
      const els = [
        rect(x, 1.55, 1.62, 1.55, fill, { round: 0.08 }),
        text(x + 0.08, 1.65, 1.46, 0.6, head, { size: 14, bold: true, color: "background1", align: "center", valign: "middle" }),
        text(x + 0.08, 2.3, 1.46, 0.75, sub, { size: 12, color: "background2", align: "center" }),
        text(x, 3.5, 1.62, 0.65, risk, { size: 12, bold: true, color: "accent3", align: "center" }),
      ];
      if (i < chain.length - 1) els.push({ type: "arrow", x: x + 1.64, y: 2.33, w: 0.18, color: "text2" });
      return els;
    }),
    text(0.5, 3.2, 4, 0.28, "Where it goes wrong", { size: 12, bold: true, color: "text2" }),
    text(0.5, 4.35, 9, 0.4, "SWIFT carries the instruction. Banks settle between their own accounts.",
      { size: 16, bold: true, color: "text1", valign: "middle" }),
    text(0.5, 4.8, 9, 0.4, "StudyRoute simulates this chain with invented banks. It moves no real money.",
      { size: 14, italic: true, color: "accent1", valign: "middle" }),
  ],
});

// 5 ---------------------------------------------------------------------------------------------
const steps = [
  ["AGENT", "Reads one sentence, makes the quote"], ["AGENT", "Ranks, plans deadline, checks KYC"],
  ["YOU", "Create a draft, choose recipient"], ["AGENT", "Gates: KYC, allowlist, caps"],
  ["YOU", "Approve with a fresh MFA code"], ["AGENT", "Tracks to SETTLED, seals a report"],
];
slides.push({
  layout: "content", section: "The solution", title: "From question to settled payment",
  notes:
    "This is task completion. On the left, the parent typed one sentence into the chat: I need to pay ten thousand pounds of tuition by 28 October. " +
    "The agent read it, made the quote, ranked the providers, planned the deadline and checked KYC, the recipient and the documents, and it built this plan card from the engine's output. " +
    "The person creates the draft, chooses the recipient and approves with a fresh MFA code. " +
    "The agent blocks the payment until KYC, the allowlist and the sandbox caps pass, then tracks it to settled and seals a compliance report. " +
    "Look at what the agent did not do: it created no payment. It can propose a draft, but a person always clicks.",
  elements: [
    ...shot("17-agent-plan.png", 0.58, 1.43, 4.34, 3.39, "The assistant's payment plan built from one sentence"),
    text(0.5, 4.95, 4.5, 0.3, "One sentence in the chat. Synthetic data.", { size: 11, color: "text2" }),
    ...steps.flatMap(([who, label], i) => {
      const y = 1.45 + i * 0.6;
      return [
        rect(5.35, y + 0.06, 0.78, 0.32, who === "AGENT" ? "accent1" : "text1", { round: 0.08 }),
        text(5.35, y + 0.06, 0.78, 0.32, who, { size: 11, bold: true, color: "background1", align: "center", valign: "middle" }),
        text(6.28, y, 3.25, 0.44, label, { size: 14, color: "text1", valign: "middle" }),
      ];
    }),
    text(5.35, 5.0, 4.2, 0.3, "AGENT: StudyRoute does it. YOU: a person decides.", { size: 11, color: "text2" }),
  ],
});

// 6 ---------------------------------------------------------------------------------------------
const split = [["FX margin", 16000, "accent1", 63], ["Fixed fee", 3000, "accent4", 12], ["SWIFT fee", 1500, "accent2", 6], ["OUR fees", 4800, "accent3", 19]];
slides.push({
  layout: "content", section: "The solution", title: "The engine does the maths",
  notes:
    "Every number comes from a deterministic engine: integer minor units, decimal rates, no floats. For one provider, total cost is the FX margin plus the fixed fee, the SWIFT fee, any fees the sender pays under OUR, " +
    "plus a shortfall when fees are deducted from the amount. We rank by that percentage. In our synthetic example, Provider B is first at 1.58 percent, " +
    "Provider C looks cheap but it is quoted as SHA, so the university would receive 35 pounds less, and Provider A is third at 2.16 percent. " +
    "On the right is where Provider B's 25,300 taka goes: most of it is the margin. " +
    "The same engine powers the smart send plan, names the cheapest provider that arrives before the due date, and can stress-test a quote if the taka weakens. A student guide shows which student cities a monthly budget covers, with invented figures marked not verified. It does not predict exchange rates, and says so.",
  elements: [
    {
      type: "table", x: 0.5, y: 1.4, colW: [0.95, 0.75, 1.1, 0.85, 1.65], rowH: 0.5, size: 14,
      rows: [
        ["Provider", "Charge", "Shortfall", "Cost %", "You pay"].map((t) => ({ text: t, bold: true, color: "background1", fill: "text1" })),
        [{ text: "B (1st)", bold: true, fill: "background2" }, { text: "OUR", fill: "background2" }, { text: "none", fill: "background2" },
          { text: "1.58%", bold: true, fill: "background2" }, { text: "BDT 1,625,300", fill: "background2" }],
        [{ text: "C (2nd)", bold: true }, { text: "SHA" }, { text: "GBP 35", bold: true, color: "accent3" }, { text: "1.63%", bold: true }, { text: "BDT 1,620,500" }],
        [{ text: "A (3rd)", bold: true }, { text: "OUR" }, { text: "none" }, { text: "2.16%", bold: true }, { text: "BDT 1,634,500" }],
      ],
    },
    text(0.5, 3.6, 5.3, 0.8,
      "Cost % = (FX margin + fixed fee + SWIFT fee + fees you pay + shortfall) / amount at the mid-market rate",
      { size: 12, color: "text2" }),
    text(0.5, 4.45, 5.3, 0.65,
      "Smart send plan: the same GBP 12,000 costs BDT 68,400 sent monthly and BDT 28,500 sent at once. Also: the cheapest that arrives before the due date, and a currency-drop stress test. Synthetic rates.",
      { size: 12, bold: true, color: "text1" }),
    text(6.1, 1.35, 3.4, 0.5, "Where Provider B's BDT 25,300 goes", { size: 14, bold: true, color: "text1" }),
    { type: "doughnut", x: 6.6, y: 1.9, w: 2.1, h: 2.1, values: split.map((s) => s[1]), colors: split.map((s) => s[2]) },
    text(6.6, 2.65, 2.1, 0.6, "BDT 25,300", { size: 14, bold: true, color: "text1", align: "center", valign: "middle" }),
    ...split.flatMap(([label, , fill, pct], i) => {
      const x = 6.1 + (i % 2) * 1.75;
      const y = 4.2 + Math.floor(i / 2) * 0.45;
      return [rect(x, y + 0.1, 0.16, 0.16, fill), text(x + 0.24, y, 1.5, 0.36, `${label} ${pct}%`, { size: 12, color: "text1", valign: "middle" })];
    }),
  ],
});

// 7 ---------------------------------------------------------------------------------------------
const proven = [
  `Every number comes from one engine, in integer money. ${F.backendTests} backend tests cover all ${F.scenarios} scenarios.`,
  "Only a human with a fresh MFA code can approve. The AI has no such permission, and a test enforces the table.",
  "Edit one audit row and Verify fails at that event. A rewritten chain is caught by the anchor.",
  "The whole stack starts from the zipped archive with docker compose, run for real on 15 and 17 October.",
];
const notProven = [
  "Rates, fees and city costs are invented. We have not compared them with real quotes yet.",
  "No real parent has used it. The trained models saw synthetic data.",
  "No outside security review or penetration test.",
  "Bangladesh Bank limits are placeholders, marked Not verified.",
];
slides.push({
  layout: "content", section: "Trust", title: "Proven, and not proven yet",
  notes:
    "Before the details, here is what we have shown and what we have not. " +
    `What we have shown: every number comes from one deterministic engine, with ${F.backendTests} backend tests covering all ${F.scenarios} scenarios. Only a human with a fresh MFA code can approve, and the AI has no such permission. ` +
    "Change one audit row and Verify fails at that event. And the stack starts from the zipped archive with one command. " +
    "What we have not shown: the rates, fees and city costs are invented, and we have not yet compared them with real quotes. No real parent has used it. No outsider has reviewed its security. The Bangladesh Bank limits are placeholders, marked Not verified. " +
    "Both lists are in the repository, because we would rather you hear the limits from us.",
  elements: [
    card(0.5, 1.35, 4.4, 3.45),
    rect(0.7, 1.5, 0.12, 0.4, "accent1"),
    text(0.92, 1.45, 3.8, 0.5, "Proven by tests and logs", { size: 18, bold: true, color: "accent1", valign: "middle" }),
    text(0.7, 2.1, 4.0, 2.6,
      proven.map((t, i) => ({ text: t, bullet: true, breakLine: i < proven.length - 1 })),
      { size: 12, color: "text1", paraAfter: 6 }),
    card(5.1, 1.35, 4.4, 3.45),
    rect(5.3, 1.5, 0.12, 0.4, "accent3"),
    text(5.52, 1.45, 3.8, 0.5, "Not proven, and we say so", { size: 18, bold: true, color: "accent3", valign: "middle" }),
    text(5.3, 2.1, 4.0, 2.6,
      notProven.map((t, i) => ({ text: t, bullet: true, breakLine: i < notProven.length - 1 })),
      { size: 12, color: "text1", paraAfter: 6 }),
    text(0.5, 4.95, 9, 0.35, "Both lists are in the repository: docs/OPEN_QUESTIONS.md and docs/SECURITY_SELF_ASSESSMENT.md",
      { size: 12, color: "text2" }),
  ],
});

// 8 ---------------------------------------------------------------------------------------------
const pipeline =["1  Policy check", "2  Engine facts", "3  Mask personal data", "4  Model (optional)", "5  Number guard", "6  Tool guard", "7  Audit"];
const guarantees = [
  ["Every number comes from the engine", "A number guard rejects any figure the engine did not produce, then a template answer takes over."],
  ["It can only propose", "It may make a quote. It cannot create a payment, approve, submit or cancel. A human approves with MFA."],
  ["Works with no key", "Template mode runs the same checks. A real model is one command away: check_ai."],
];
slides.push({
  layout: "content", section: "Trust", title: "An AI that cannot cheat",
  notes:
    "The assistant follows a fixed pipeline. A policy check flags attempts to override rules, approve or reveal secrets, and a flagged message never reaches the model. " +
    "Facts come only from the engine. Personal data is masked before any model call. The model is the only step that is not deterministic, and it is optional. " +
    "Then a number guard checks every figure in the reply against the engine's facts and falls back to a template if anything is invented, a tool guard allows only proposals, and everything is audited. " +
    "So: every number comes from the engine, the AI can only propose, and it works with no API key at all.",
  elements: [
    ...pipeline.flatMap((label, i) => {
      const x = 0.5 + i * 1.3;
      const model = i === 3;
      return [
        rect(x, 1.4, 1.15, 0.8, model ? "accent2" : "text1", { round: 0.08 }),
        text(x + 0.05, 1.4, 1.05, 0.8, label, { size: 12, bold: true, color: model ? "text1" : "background1", align: "center", valign: "middle" }),
      ];
    }),
    text(0.5, 2.28, 9, 0.32, "Only step 4 is not deterministic, and it is optional. A flagged message never reaches it.", { size: 12, color: "text2" }),
    ...guarantees.flatMap(([head, body], i) => {
      const x = 0.5 + i * 3.05;
      return [
        card(x, 2.75, 2.9, 2.4),
        text(x + 0.2, 2.9, 2.5, 0.7, head, { size: 16, bold: true, color: "text1" }),
        text(x + 0.2, 3.65, 2.5, 1.4, body, { size: 14, color: "text2" }),
      ];
    }),
  ],
});

// 9 ---------------------------------------------------------------------------------------------
const blind = { rules: AI.results.rules.blind, agent: AI.results.agent.blind };
const pc = (v) => `${(100 * v).toFixed(1).replace(/\.0$/, "")}%`;
const rlBefore = RL.results["before: plan as soon as the amount is known"];
const rlLearned = RL.results["RL policy (shipped)"];
const riskRoute = RISK["routing used by the review desk"]["medium or high (a person looks)"];
const trained = [
  ["What it does", `Reads the intent and marks the words that carry an amount, a currency or a date. It proposes; plain code checks; the engine calculates. A GPU run of a few minutes on ${AI.data.train.toLocaleString("en-US")} messages; ${(AI.model_bytes / 1e6).toFixed(0)} MB, ${Math.round(AI.latency_cpu.median_ms)} ms on a CPU.`],
  ["Reinforcement learning", `A policy trained by Double DQN decides when to ask, read back or plan. On simulated parents: wrong plans ${pc(rlLearned.wrong_plan)} against ${pc(rlBefore.wrong_plan)}, ${rlLearned.turns.toFixed(2)} questions against ${rlBefore.turns.toFixed(2)}. Code limits its legal moves.`],
  ["Also trained, and the limits", `A language model rewords answers (${pc(EXPL.shipped_model.raw_output.figure_precision)} of its figures are the engine's; a failed check shows the engine's text). A risk model scores every payment (amount, frequency, timeline, person) and warns on a high one: precision ${pc(riskRoute.precision)}, recall ${pc(riskRoute.recall)}. Every payment needs a person's authorization anyway. Synthetic data, no real users.`],
];
slides.push({
  layout: "content", section: "Trust", title: "Trained agents, measured",
  notes:
    "The assistant has a trained component, and we measured it. A small language model, fine-tuned on a gaming-class GPU in a few minutes, reads what a parent types: the intent, and the exact words that carry an amount, a currency or a date. It never produces a number; plain code turns those words into values, and when the old rules and the model disagree, the assistant asks. " +
    `On messages we wrote by hand after the model was frozen, it chose the right intent ${pc(blind.agent.routing_accuracy)} of the time against ${pc(blind.rules.routing_accuracy)} for the old rules, ` +
    `read a plan request exactly ${pc(blind.agent.task_success)} against ${pc(blind.rules.task_success)}, and blocked ${pc(blind.agent.attack_blocked)} of attacks against ${pc(blind.rules.attack_blocked)}. The sample is small and the data is synthetic. ` +
    `A second small policy, trained with reinforcement learning, chooses whether to ask, read back or plan: on simulated parents, wrong plans fell from ${pc(rlBefore.wrong_plan)} to ${pc(rlLearned.wrong_plan)}. Plain code limits its legal moves, and the parents are our assumption. ` +
    `Two more small models are trained on the same GPU. A language model rewords the engine's answer on the user's own machine: on ${EXPL.test_pairs} held-out questions ${pc(EXPL.shipped_model.shown_share)} of its answers pass every code check and the rest show the engine's own text; ${pc(EXPL.shipped_model.raw_output.figure_precision)} of the figures it writes are the engine's. It mostly rewords. A risk model, trained on IBM's public synthetic transactions, gives each payment a score from four factors, amount, frequency, timeline and person: a low score shows no warning, a high one shows a warning and sends the payment to a person at the sandbox bank, and every payment needs a person's authorization whatever its score; on a later period it caught ${pc(riskRoute.recall)} of the flagged payments with ${pc(riskRoute.precision)} precision, and the data cannot support both above ninety. It routes; a person decides.`,
  elements: [
    {
      type: "table", x: 0.5, y: 1.4, colW: [2.1, 1.1, 1.1], rowH: 0.55, size: 14,
      rows: [
        ["On 113 new messages", "Rules", "Agent"].map((t) => ({ text: t, bold: true, color: "background1", fill: "text1" })),
        [{ text: "Right intent", fill: "background2" }, { text: pc(blind.rules.routing_accuracy), fill: "background2" }, { text: pc(blind.agent.routing_accuracy), bold: true, color: "accent1", fill: "background2" }],
        [{ text: "Plan read exactly" }, { text: pc(blind.rules.task_success) }, { text: pc(blind.agent.task_success), bold: true, color: "accent1" }],
        [{ text: "Attacks blocked", fill: "background2" }, { text: pc(blind.rules.attack_blocked), fill: "background2" }, { text: pc(blind.agent.attack_blocked), bold: true, color: "accent1", fill: "background2" }],
        [{ text: "Harmless blocked" }, { text: pc(blind.rules.benign_blocked) }, { text: pc(blind.agent.benign_blocked), bold: true }],
      ],
    },
    text(0.5, 4.3, 4.4, 0.9,
      `Written by hand after the model was frozen, scored once. A small sample: about plus or minus 7 points. Real bank questions: rules ${pc(AI.results.rules.natural.routing_accuracy)}, agent ${pc(AI.results.agent.natural.routing_accuracy)}.`,
      { size: 12, color: "text2" }),
    ...trained.flatMap(([head, body], i) => {
      const y = 1.4 + i * 1.25;
      return [
        card(5.3, y, 4.2, 1.15),
        text(5.45, y + 0.04, 3.9, 0.3, head, { size: 14, bold: true, color: "accent1" }),
        text(5.45, y + 0.36, 3.95, 0.78, body, { size: 11, color: "text1" }),
      ];
    }),
  ],
});

// 10 --------------------------------------------------------------------------------------------
const tiers = [
  ["Public:", " sign in, health", "background2", "text1"],
  ["Read:", " own household only", "background2", "text1"],
  ["Prepare:", " drafts, recipients, documents", "background2", "text1"],
  ["Decide:", " human parent with fresh MFA", "accent1", "background1"],
  ["Administer:", " reviewer rules and Verify", "background2", "text1"],
  ["Never for the AI:", " approve, cancel, limits", "accent3", "background1"],
];
const stats = [
  [String(F.backendTests), "backend tests, all passing"], [String(F.frontendTests), "frontend tests"],
  [`${F.scenarios} of 24`, "blueprint scenarios mapped to tests"], [String(F.risks), "known risks listed openly"],
];
slides.push({
  layout: "content", section: "Trust", title: "Security you can verify",
  notes:
    "Security and compliance is thirty percent of the score, so we made it checkable. On the left are the permission tiers, enforced in the domain layer, not just in the screens. " +
    "Public, read, prepare, decide, and administer. Deciding, meaning approving a payment, is only for a human parent with a fresh MFA proof bound to that payment and to the hash of the summary they saw. " +
    "The AI has no approve, cancel, limit or config permission at all. On the right, the numbers: " +
    `${F.backendTests} backend and ${F.frontendTests} frontend tests, all ${F.scenarios} blueprint scenarios mapped to tests, and ${F.risks} known risks that we list openly in the self-assessment. ` +
    "The audit log is hash-chained: Verify passes, we edit one row behind the application's back, and Verify fails at exactly that event.",
  elements: [
    ...tiers.flatMap(([lead, rest, fill, color], i) => {
      const y = 1.4 + i * 0.52;
      return [
        rect(0.5, y, 4.4, 0.44, fill, { round: 0.06 }),
        text(0.65, y, 4.15, 0.44, [{ text: lead, bold: true }, { text: rest }], { size: 14, color, valign: "middle" }),
      ];
    }),
    ...stats.flatMap(([num, label], i) => {
      const x = 5.1 + (i % 2) * 2.3;
      const y = 1.4 + Math.floor(i / 2) * 1.5;
      return [
        card(x, y, 2.1, 1.3),
        text(x + 0.15, y + 0.1, 1.8, 0.65, num, { size: 32, bold: true, font: "+mj-lt", color: "accent1", valign: "middle" }),
        text(x + 0.15, y + 0.75, 1.8, 0.5, label, { size: 12, color: "text2" }),
      ];
    }),
    text(5.1, 4.45, 4.4, 0.75,
      "Each payment has a compliance report with a hash your browser can check. Every threat has a test: docs/SECURITY.md",
      { size: 12, color: "text2" }),
  ],
});

// 11 --------------------------------------------------------------------------------------------
slides.push({
  layout: "content", section: "Trust", title: "Honest by design",
  notes:
    "Honesty is a feature. A banner on every screen and an X-Sandbox header on every API response say this is a sandbox. " +
    "The Sandbox screen on the left lists everything that is simulated and how to trigger the edge cases, such as a recipient named FAIL_TEST. " +
    "Any rule that has not been checked against an official source carries a yellow Not verified badge and the sentence: indicative, confirm with your AD bank. " +
    "On the right is a payment's compliance report: the parties, ten controls with their evidence, the approval proof and the audit trail, sealed with a hash that the browser recomputes. Change a copy and it says does not match.",
  elements: [
    text(0.5, 1.2, 9, 0.4, "Every simulated part is labelled. Every unverified rule carries a badge.", { size: 16, bold: true, color: "text1", valign: "middle" }),
    ...shot("15-sandbox-admin.png", 0.58, 1.78, 4.0, 3.12, "Sandbox screen listing what is simulated"),
    ...shot("20-compliance-report.png", 5.42, 1.78, 4.0, 3.12, "Compliance report whose hash verifies in the browser"),
    text(0.5, 5.02, 4.16, 0.3, "Sandbox screen: what is simulated, how to test it", { size: 11, color: "text2" }),
    text(5.34, 5.02, 4.16, 0.3, "Compliance report: the hash verifies in the browser", { size: 11, color: "text2" }),
  ],
});

// 12 --------------------------------------------------------------------------------------------
const next = [
  ["Verified rules", "Replace each placeholder rule with an official Bangladesh Bank source."],
  ["A real AD bank partner", "Real quotes, real KYC, and regulator-ready reports from the audit log."],
  ["Credit building", "Topic C scope we have not built: help a student build a credit history abroad."],
  ["A real chain", "Escrow already runs in the sandbox. Next: a permissioned chain and a bank-issued token."],
];
slides.push({
  layout: "closing", section: "Close", title: "What comes next",
  notes:
    "Next steps. First, replace every placeholder rule with an official Bangladesh Bank source and add the moon-dependent holidays. " +
    "Second, a partnership with an authorised dealer bank for real quotes and real KYC, and regulator-ready reports from the audit log. " +
    "Third, beyond tuition, the sandbox already has a smart escrow for living costs and a bank-network simulation; the escrow contracts would move from our simulated chain to a permissioned one with a deposit token issued by a bank. " +
    "Topic C also mentions credit building. We have not built it, and we would rather say so than pretend. We do show a household's money in every currency, but those are simulated accounts, not real ones. " +
    "To close: StudyRoute is clear, cheap and safe, because the engine calculates, the AI explains, the human approves, and every step is logged. Thank you.",
  elements: [
    ...next.flatMap(([head, body], i) => {
      const x = i % 2 === 0 ? 0.5 : 5.1;
      const y = 1.35 + Math.floor(i / 2) * 1.4;
      return [
        rect(x, y, 4.4, 1.25, "text2", { round: 0.08 }),
        text(x + 0.2, y + 0.1, 4.0, 0.4, head, { size: 18, bold: true, color: "background1", valign: "middle" }),
        text(x + 0.2, y + 0.5, 4.0, 0.7, body, { size: 14, color: "background2" }),
      ];
    }),
    text(0.5, 4.25, 9, 0.55, "Clear, cheap and safe.", { size: 24, bold: true, font: "+mj-lt", color: "accent2", valign: "middle" }),
    text(0.5, 4.85, 9, 0.35, `${TEAM}  ·  ${REPO}  ·  Sandbox: no real money moves`, { size: 12, color: "accent5" }),
  ],
});

// ---------------------------------------------------------------------------------------------
// Renderer 1: PowerPoint
// ---------------------------------------------------------------------------------------------
async function writePptx() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9"; // 10 in x 5.625 in
  pres.title = "StudyRoute: sandbox AI agent for tuition payments from Bangladesh";
  pres.subject = "FinTechathon 2026, International Track, Topic C";
  pres.author = TEAM;
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;
  const color = (token) => C[token];

  for (const [name, spec] of Object.entries(LAYOUTS)) {
    pres.defineSlideMaster({
      title: name.toUpperCase(),
      background: { color: hexOf(spec.bg) },
      objects: [{
        placeholder: {
          options: {
            name: "title", type: "title", ...spec.titleBox, fontFace: "+mj-lt", fontSize: spec.titleSize,
            bold: true, color: color(spec.titleColor), align: "left", valign: "middle", margin: 0,
          },
          text: "",
        },
      }],
    });
  }

  const sections = [...new Set(slides.map((s) => s.section))];
  for (const title of sections) pres.addSection({ title });

  for (const s of slides) {
    const slide = pres.addSlide({ masterName: s.layout.toUpperCase(), sectionTitle: s.section });
    slide.addText(s.title, { placeholder: "title" });
    let n = 0;
    for (const e of s.elements) addElement(pres, slide, color, e, `${s.layout}-${slides.indexOf(s) + 1}-${e.type}-${++n}`);
    slide.addNotes(s.notes);
  }
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT);
}

function shadow() {
  return { type: "outer", color: "0B2545", blur: 8, offset: 2, angle: 90, opacity: 0.18 };
}

function textRuns(e, color) {
  const base = { fontSize: e.size, color: color(e.color || "text1"), bold: !!e.bold, italic: !!e.italic };
  if (e.font) base.fontFace = e.font;
  return e.runs.map((r) => {
    const options = { ...base };
    if (r.bold !== undefined) options.bold = r.bold;
    if (r.italic !== undefined) options.italic = r.italic;
    if (r.color) options.color = color(r.color);
    if (r.bullet) options.bullet = true;
    if (r.breakLine) options.breakLine = true;
    return { text: r.text, options };
  });
}

function addElement(pres, slide, color, e, name) {
  const pos = { x: e.x, y: e.y, w: e.w, h: e.h };
  if (e.type === "rect" || e.type === "oval") {
    const shape = e.type === "oval" ? pres.ShapeType.ellipse : e.round ? pres.ShapeType.roundRect : pres.ShapeType.rect;
    const options = { ...pos, fill: { color: color(e.fill) }, line: e.line ? { color: color(e.line), width: 0.75 } : { type: "none" }, objectName: name };
    if (e.round && e.type === "rect") options.rectRadius = e.round;
    if (e.shadow) options.shadow = shadow();
    slide.addShape(shape, options);
  } else if (e.type === "text") {
    slide.addText(textRuns(e, color), {
      ...pos, margin: 0, isTextBox: true, align: e.align || "left", valign: e.valign || "top",
      paraSpaceAfter: e.paraAfter || 0, fit: "none", objectName: name,
    });
  } else if (e.type === "image") {
    slide.addImage({ path: e.file, ...pos, altText: e.alt, objectName: name });
  } else if (e.type === "arrow") {
    slide.addShape(pres.ShapeType.line, {
      x: e.x, y: e.y, w: e.w, h: 0, line: { color: color(e.color), width: 2, endArrowType: "triangle" }, objectName: name,
    });
  } else if (e.type === "table") {
    const rows = e.rows.map((row) => row.map((cell) => ({
      text: cell.text,
      options: {
        bold: !!cell.bold, color: color(cell.color || "text1"), align: "left", valign: "middle",
        fill: cell.fill ? { color: color(cell.fill) } : undefined,
      },
    })));
    slide.addTable(rows, {
      x: e.x, y: e.y, w: e.colW.reduce((a, b) => a + b, 0), colW: e.colW, rowH: e.rowH, fontSize: e.size,
      border: { type: "solid", pt: 0.75, color: THEME.colors.accent5 }, objectName: name,
    });
  } else if (e.type === "doughnut") {
    slide.addChart(pres.charts.DOUGHNUT, [{ name: "Cost", labels: ["FX margin", "Fixed fee", "SWIFT fee", "OUR fees"], values: e.values }], {
      ...pos, holeSize: 58, showLegend: false, showTitle: false, showPercent: false, showValue: false, showLabel: false,
      chartColors: e.colors.map(hexOf), dataBorder: { pt: 2, color: "FFFFFF" },
    });
  } else {
    throw new Error(`Unknown element type ${e.type}`);
  }
}

// Our own small theme writer: put the deck's colours into ppt/theme/theme1.xml.
async function applyTheme(file) {
  const JSZip = require("jszip");
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const part = "ppt/theme/theme1.xml";
  const slots = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"];
  const scheme = `<a:clrScheme name="${THEME.name}">` +
    slots.map((k) => `<a:${k}><a:srgbClr val="${THEME.colors[k]}"/></a:${k}>`).join("") + "</a:clrScheme>";
  let xml = await zip.file(part).async("string");
  xml = xml.replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => scheme);
  xml = xml.replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, head) => `${head}${THEME.name}"`);
  zip.file(part, xml);
  for (const name of Object.keys(zip.files)) {
    if (!name.endsWith(".xml")) continue;
    const bad = (await zip.file(name).async("string")).match(/<a:srgbClr val="((?![0-9A-Fa-f]{6}")[^"]*)"/);
    if (bad) throw new Error(`${name} has a colour that is not six hex digits: "${bad[1]}". A scheme colour went to a hex-only option.`);
  }
  fs.writeFileSync(file, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

// ---------------------------------------------------------------------------------------------
// Renderer 2: HTML preview of the same model (for looking at slides without PowerPoint)
// ---------------------------------------------------------------------------------------------
function writePreview(folder) {
  const PX = 96;
  const px = (inches) => `${(inches * PX).toFixed(2)}px`;
  const pt = (points) => `${(points * PX / 72).toFixed(2)}px`;
  const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const family = (font) => (font === "+mj-lt" ? "Cambria, serif" : "Calibri, sans-serif");
  const box = (e) => `left:${px(e.x)};top:${px(e.y)};width:${px(e.w)};height:${px(e.h)};`;

  const html = (e, layoutName) => {
    if (e.type === "rect" || e.type === "oval") {
      const radius = e.type === "oval" ? "50%" : e.round ? px(e.round) : "0";
      const border = e.line ? `border:0.75pt solid #${hexOf(e.line)};` : "";
      const shadowCss = e.shadow ? "box-shadow:0 2px 8px rgba(11,37,69,.18);" : "";
      return `<div class="el" style="${box(e)}background:#${hexOf(e.fill)};border-radius:${radius};${border}${shadowCss}"></div>`;
    }
    if (e.type === "text") {
      const anchor = { top: "flex-start", middle: "center", bottom: "flex-end" }[e.valign || "top"];
      const paras = [[]];
      for (const r of e.runs) { paras[paras.length - 1].push(r); if (r.breakLine) paras.push([]); }
      const body = paras.filter((p) => p.length).map((p) => {
        const bullet = p.some((r) => r.bullet);
        const spans = p.map((r) => {
          const bold = r.bold !== undefined ? r.bold : e.bold;
          const italic = r.italic !== undefined ? r.italic : e.italic;
          return `<span style="color:#${hexOf(r.color || e.color || "text1")};font-weight:${bold ? 700 : 400};font-style:${italic ? "italic" : "normal"}">${esc(r.text)}</span>`;
        }).join("");
        return `<p class="${bullet ? "bul" : ""}" style="margin:0 0 ${pt(e.paraAfter || 0)};">${spans}</p>`;
      }).join("");
      return `<div class="el txt" data-name="${esc(e.runs.map((r) => r.text).join("").slice(0, 40))}" style="${box(e)}display:flex;flex-direction:column;justify-content:${anchor};text-align:${e.align || "left"};font-size:${pt(e.size)};font-family:${family(e.font)};line-height:1.2;">${body}</div>`;
    }
    if (e.type === "image") return `<img class="el" style="${box(e)}object-fit:fill;" src="file:///${e.file.replace(/\\/g, "/")}" alt="${esc(e.alt)}">`;
    if (e.type === "arrow") return `<div class="el" style="left:${px(e.x)};top:${px(e.y)};width:${px(e.w)};height:0;border-top:2pt solid #${hexOf(e.color)};"></div><div class="el" style="left:${px(e.x + e.w - 0.07)};top:${px(e.y - 0.06)};width:0;height:0;border-left:${px(0.09)} solid #${hexOf(e.color)};border-top:${px(0.06)} solid transparent;border-bottom:${px(0.06)} solid transparent;"></div>`;
    if (e.type === "table") {
      const width = e.colW.reduce((a, b) => a + b, 0);
      const rows = e.rows.map((row) => `<tr style="height:${px(e.rowH)}">${row.map((c, i) => `<td style="width:${px(e.colW[i])};background:${c.fill ? "#" + hexOf(c.fill) : "transparent"};color:#${hexOf(c.color || "text1")};font-weight:${c.bold ? 700 : 400};border:0.75pt solid #${THEME.colors.accent5};padding:0 0.1in;">${esc(c.text)}</td>`).join("")}</tr>`).join("");
      return `<table class="el" style="left:${px(e.x)};top:${px(e.y)};width:${px(width)};border-collapse:collapse;table-layout:fixed;font-size:${pt(e.size)};font-family:Calibri,sans-serif;">${rows}</table>`;
    }
    if (e.type === "doughnut") {
      const total = e.values.reduce((a, b) => a + b, 0);
      let at = 0;
      const stops = e.values.map((v, i) => { const from = (at / total) * 360; at += v; return `#${hexOf(e.colors[i])} ${from}deg ${(at / total) * 360}deg`; }).join(",");
      const hole = e.w * 0.58;
      return `<div class="el" style="${box(e)}border-radius:50%;background:conic-gradient(${stops});"></div><div class="el" style="left:${px(e.x + (e.w - hole) / 2)};top:${px(e.y + (e.h - hole) / 2)};width:${px(hole)};height:${px(hole)};border-radius:50%;background:#${hexOf("background1")};"></div>`;
    }
    throw new Error(`Unknown element type ${e.type} in ${layoutName}`);
  };

  const page = slides.map((s, i) => {
    const L = LAYOUTS[s.layout];
    const t = { x: L.titleBox.x, y: L.titleBox.y, w: L.titleBox.w, h: L.titleBox.h };
    const title = `<div class="el txt" data-name="TITLE ${esc(s.title)}" style="${box(t)}display:flex;align-items:center;font-size:${pt(L.titleSize)};font-weight:700;font-family:Cambria,serif;color:#${hexOf(L.titleColor)};line-height:1.2;">${esc(s.title)}</div>`;
    return `<section class="slide" id="s${i + 1}" style="background:#${hexOf(L.bg)};">${title}${s.elements.map((e) => html(e, s.layout)).join("")}</section>`;
  }).join("\n");

  fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(path.join(folder, "preview.html"), `<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#888;}
.slide{position:relative;width:960px;height:540px;margin:0 0 12px 0;overflow:hidden;}
.el{position:absolute;box-sizing:border-box;}
.txt{overflow:hidden;}
td{box-sizing:border-box;}
.bul{padding-left:0.25in;text-indent:-0.25in;}
.bul::before{content:"\\2022\\00a0\\00a0";}
img.el{display:block;}
</style>${page}`);
}

(async () => {
  await writePptx();
  console.log(`Wrote ${path.relative(ROOT, OUT)} (${slides.length} slides).`);
  const at = process.argv.indexOf("--preview");
  if (at !== -1) {
    writePreview(process.argv[at + 1]);
    console.log(`Wrote preview.html to ${process.argv[at + 1]}`);
  }
})().catch((error) => { console.error(error.message); process.exit(1); });
