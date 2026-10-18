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
    return Number(m[1].replace(/,/g, ""));
  };
  const assessment = read("docs/SECURITY_SELF_ASSESSMENT.md");
  return {
    backendTests: grab(/([\d,]+) backend tests/, "backend count"),
    frontendTests: grab(/Frontend: \*\*(\d+) tests\*\*/, "frontend count"),
    scenarios: (cases.match(/^\| T\d\d \|/gm) || []).length,
    risks: (assessment.match(/^\| R\d+ \|/gm) || []).length,
  };
}
const AI = JSON.parse(read("submission/evidence/ai_evaluation.json"));
const RL = JSON.parse(read("submission/evidence/ai_rl_evaluation.json"));
const EXPL = JSON.parse(read("submission/evidence/ai_explainer_evaluation.json"));
const RISK = JSON.parse(read("submission/evidence/ai_risk_operating_points.json"));
const RISKTRAIN = JSON.parse(read("submission/evidence/ai_risk_training.json"));
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


// Screenshots of the public deployment (taken on 19 Oct 2026) live in submission/screenshots/live/.
// liveShot keeps the picture's own proportions: give it the width and it returns the frame, the image and the height used.
function pngSize(file) {
  const bytes = fs.readFileSync(path.join(SHOTS, file));
  return { w: bytes.readUInt32BE(16), h: bytes.readUInt32BE(20) };
}
function liveShot(file, x, y, w, alt) {
  const size = pngSize(path.join("live", file));
  const h = (w * size.h) / size.w;
  return { h, els: shot(path.join("live", file), x, y, w, h, alt) };
}

// Horizontal bars drawn from plain shapes, so they look the same in every viewer.
// rows: [{ label, parts: [{ value, fill, text }] }]; one part per row, or two for a pair of bars to compare.
function hbars({ x, y, w, labelW, valueW, max, rows, rowH, barH, size = 11 }) {
  const els = [];
  const track = w - labelW - valueW;
  rows.forEach((row, i) => {
    const top = y + i * rowH;
    const total = row.parts.length * barH + (row.parts.length - 1) * 0.05;
    els.push(text(x, top, labelW - 0.1, rowH, row.label, { size, color: "text1", valign: "middle" }));
    row.parts.forEach((part, j) => {
      const by = top + (rowH - total) / 2 + j * (barH + 0.05);
      const bw = Math.max(0.04, (track * part.value) / max);
      els.push(rect(x + labelW, by, bw, barH, part.fill, { round: 0.03 }));
      els.push(text(x + labelW + bw + 0.08, by, valueW + 0.2, barH, part.text, { size: size - 1, bold: true, color: "text1", valign: "middle" }));
    });
  });
  return els;
}
const legend = (x, y, items) => items.flatMap(([label, fill], i) => [
  rect(x + i * 1.7, y + 0.06, 0.16, 0.16, fill),
  text(x + i * 1.7 + 0.24, y, 1.45, 0.28, label, { size: 10, color: "text2", valign: "middle" }),
]);
const bullets = (items) => items.map((t, i) => ({ text: t, bullet: true, breakLine: i < items.length - 1 }));

const LIVE_SITE = "studyroute.bot-keep.xyz";
const slides = [];

// 1 ---------------------------------------------------------------------------------------------
slides.push({
  layout: "title", section: "Opening", title: "StudyRoute",
  notes:
    "Good morning. We are team " + TEAM + ", and this is StudyRoute, our Topic C entry: a sandbox AI agent that helps a parent in Bangladesh pay tuition abroad. Everything is synthetic, no real money moves, and it runs live at studyroute dot bot-keep dot xyz. Our rule: the engine calculates, the AI explains, the human approves, every step is logged.",
  elements: [
    text(0.6, 0.55, 6.0, 0.3, "TOPIC C  ·  CROSS-BORDER AND STUDENT FINANCE ASSISTANT", { size: 12, bold: true, color: "accent2" }),
    text(0.6, 2.35, 5.7, 1.3,
      "An AI agent that helps a parent in Bangladesh pay tuition abroad: clear costs, safe approval, full audit.",
      { size: 20, color: "background2" }),
    text(0.6, 3.85, 5.7, 1.0,
      "The engine calculates. The AI explains. The human approves. Every step is logged.",
      { size: 16, italic: true, color: "accent2" }),
    text(0.6, 5.0, 5.8, 0.3, `${TEAM}  ·  Sandbox: synthetic data, no real money moves`, { size: 12, color: "accent5" }),
    ...liveShot("live-06-student-guide.png", 6.9, 0.5, 2.6, "The live student guide finding cities that fit a budget").els,
    ...liveShot("live-07-bank-network.png", 6.9, 2.2, 2.6, "The live bank network screen with invented banks").els,
    ...liveShot("live-08-smart-escrow.png", 6.9, 3.9, 2.6, "The live smart escrow screen on a simulated chain").els,
    text(0.6, 5.28, 5.8, 0.28, `Live: ${LIVE_SITE}`, { size: 11, bold: true, color: "accent2" }),
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
    "Parents compare banks by the fee they are shown. In our synthetic example, for ten thousand pounds with Provider B, 63 percent of the real cost is the hidden exchange-rate margin. Correspondent banks can deduct fees on the way, so the university may be paid short; the deadline spans two calendars; and the paperwork is unclear. Those five problems shape StudyRoute.",
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
    "Two people feel this. The parent pays in taka, compares by the posted fee, and approves a large transfer with little to check it against. The student needs the university paid on time: a short or unmatched payment means late fees and weeks of waiting. StudyRoute gives both one plan; the parent decides, and the student can see but cannot approve.",
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
    "This is the real chain: taka to an authorised dealer bank, a SWIFT instruction, a correspondent bank that may take a fee, a receiving bank that may take another, and the university matching by reference. Each step fails in a typical way, shown in red. We simulate the chain with invented banks and a double-entry ledger; no real money moves.",
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
    "This is task completion. The parent types one sentence; the agent makes the quote, ranks providers, plans the deadline, checks KYC, and builds this plan card from engine output. A person creates the draft and approves with a fresh MFA code. The agent blocks the payment until KYC, allowlist and caps pass, then tracks it to settled. It never creates a payment itself.",
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
    "Every number comes from a deterministic engine: integer money, no floats. In our synthetic example Provider B is first at 1.58 percent. Provider C looks cheap but is quoted as SHA, so the university would receive 35 pounds less. Provider A is third at 2.16. The same engine drives the send plan and the currency stress test.",
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
    text(0.5, 4.35, 5.3, 1.0,
      "Smart send plan: the same GBP 12,000 costs BDT 68,400 sent monthly and BDT 28,500 sent at once. A saving of BDT 39,900 against sending monthly (synthetic). Also: the cheapest that arrives before the due date, and a currency-drop stress test. Synthetic rates.",
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
  "Every number comes from one engine, in integer money. All 24 blueprint scenarios are mapped to tests (counts on the next slides).",
  "Only a human with a fresh MFA code can approve. The AI has no such permission, and a test enforces the table.",
  "Edit one audit row and Verify fails at that event. Audit-only rewrites are detected; both logs share SQLite, so a DB owner can rewrite both.",
  "The Docker stack passed its demo, 48 browser checks and the hardened overlay on 18 Oct; the attack probes defended 146 of 146.",
];
const notProven = [
  "Rates, fees and city costs are invented. We have not compared them with real quotes yet.",
  "No real parent has used it. The trained models saw synthetic data.",
  "Local code review and regression tests; no external penetration test.",
  "Most Bangladesh Bank figures are placeholders marked Not verified; four rules were read in the official circular.",
];
slides.push({
  layout: "content", section: "Trust", title: "Proven, and not proven yet",
  notes:
    "What we have shown: one engine for every number, a human-only approval, an audit log that fails Verify when one row is edited, a Docker run, and attack probes defended. What we have not shown: rates and costs are invented, no real parent has used it, there was no outside penetration test, and most Bangladesh Bank figures are placeholders. Both lists are in the repository.",
  elements: [
    card(0.5, 1.35, 4.4, 3.45),
    rect(0.7, 1.5, 0.12, 0.4, "accent1"),
    text(0.92, 1.45, 3.8, 0.5, "Proven by tests and logs", { size: 18, bold: true, color: "accent1", valign: "middle" }),
    text(0.7, 2.02, 4.0, 2.72,
      proven.map((t, i) => ({ text: t, bullet: true, breakLine: i < proven.length - 1 })),
      { size: 11, color: "text1", paraAfter: 4 }),
    card(5.1, 1.35, 4.4, 3.45),
    rect(5.3, 1.5, 0.12, 0.4, "accent3"),
    text(5.52, 1.45, 3.8, 0.5, "Not proven, and we say so", { size: 18, bold: true, color: "accent3", valign: "middle" }),
    text(5.3, 2.1, 4.0, 2.6,
      notProven.map((t, i) => ({ text: t, bullet: true, breakLine: i < notProven.length - 1 })),
      { size: 12, color: "text1", paraAfter: 6 }),
    text(0.5, 4.95, 9, 0.35, "Both lists are in the repository: docs/OPEN_QUESTIONS.md and docs/SECURITY_SELF_ASSESSMENT.md",
      { size: 11, color: "text2" }),
    text(0.5, 5.32, 9, 0.22, "Raw logs and reproduction commands: submission/evidence/, docs/TEST_CASES.md.", { size: 10, color: "text2" }),
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
    "The assistant follows a fixed pipeline: policy check, engine facts, masking of personal data, an optional model, a number guard, a tool guard and the audit log. Any figure the model invents is rejected, then a template answers. So the AI can only propose: it cannot approve, submit or cancel, and it works with no API key.",
  elements: [
    text(0.5, 1.16, 9, 0.3, "Our thesis: AI can participate only if it cannot be the financial authority.", { size: 13, bold: true, color: "accent1" }),
    ...pipeline.flatMap((label, i) => {
      const x = 0.5 + i * 1.3;
      const model = i === 3;
      return [
        rect(x, 1.57, 1.15, 0.65, model ? "accent2" : "text1", { round: 0.08 }),
        text(x + 0.05, 1.57, 1.05, 0.65, label, { size: 12, bold: true, color: model ? "text1" : "background1", align: "center", valign: "middle" }),
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
const rlLearned = RL.results["RL model (raw, before runtime review)"];
const riskRoute = RISK["routing used by the review desk"]["medium or high (a person looks)"];
const riskOrder = RISKTRAIN.results.mlp.test;
const riskRandom = RISKTRAIN.results.random_order.test;
const trained = [
  ["What it does", `Reads the intent and marks the words that carry an amount, a currency or a date. It proposes; plain code checks; the engine calculates. A GPU run of a few minutes on ${AI.data.train.toLocaleString("en-US")} messages; ${(AI.model_bytes / 1e6).toFixed(0)} MB, ${Math.round(AI.latency_cpu.median_ms)} ms on a CPU.`],
  ["Reinforcement learning", `A policy trained by Double DQN decides when to ask, read back or plan. On simulated parents: wrong plans ${pc(rlLearned.wrong_plan)} against ${pc(rlBefore.wrong_plan)}, ${rlLearned.turns.toFixed(2)} questions against ${rlBefore.turns.toFixed(2)}. Raw simulator only; the API now adds mandatory clarification and read-back.`],
  ["Also trained, and the limits", `A language model rewords answers: ${pc(EXPL.shipped_model.raw_output.figure_precision)} of its figures are the engine's; a failed check shows the engine's text. A risk model puts ${pc(riskOrder.found_in_top_1_percent)} of flagged payments in its top 1% (random: ${pc(riskRandom.found_in_top_1_percent)}). A person authorizes every payment. Synthetic data.`],
];
slides.push({
  layout: "content", section: "Trust", title: "Trained agents, measured",
  notes:
    "The assistant has a trained part, and we measured it, but the envelope matters more than the benchmark. A small model reads the intent and marks amounts, currencies and dates. " +
    "A reinforcement-learning policy decides when to ask, read back or plan. A third rewords the engine's answer, every rewrite checked in code; a fourth scores each payment for a person to review.",
  elements: [
    text(0.5, 1.18, 9, 0.32, "We measured the models against baselines we ran, and publish the modest results because the envelope, not the benchmark, is the contribution.", { size: 9.5, bold: true, color: "accent1" }),
    {
      type: "table", x: 0.5, y: 1.65, colW: [4.8, 2.1, 2.1], rowH: 0.31, size: 11,
      rows: [
        ["On 113 frozen messages", "Rules", "Agent"].map((t) => ({ text: t, bold: true, color: "background1", fill: "text1" })),
        [{ text: "Right intent", fill: "background2" }, { text: pc(blind.rules.routing_accuracy), fill: "background2" }, { text: pc(blind.agent.routing_accuracy), bold: true, color: "accent1", fill: "background2" }],
        [{ text: "Plan read exactly" }, { text: pc(blind.rules.task_success) }, { text: pc(blind.agent.task_success), bold: true, color: "accent1" }],
        [{ text: "Attacks blocked", fill: "background2" }, { text: pc(blind.rules.attack_blocked), fill: "background2" }, { text: pc(blind.agent.attack_blocked), bold: true, color: "accent1", fill: "background2" }],
        [{ text: "Harmless blocked" }, { text: pc(blind.rules.benign_blocked) }, { text: pc(blind.agent.benign_blocked), bold: true }],
      ],
    },
    text(0.5, 3.25, 9, 0.42,
      `Written by hand after the model was frozen, now reproduced; not a new blind study. A small sample: about plus or minus 7 points. Real bank questions: rules ${pc(AI.results.rules.natural.routing_accuracy)}, agent ${pc(AI.results.agent.natural.routing_accuracy)}.`,
      { size: 10, color: "text2" }),
    ...trained.flatMap(([head, body], i) => {
      const x = 0.5 + i * 3.05;
      const y = 3.83;
      const h = 1.48;
      return [
        card(x, y, 2.9, h),
        text(x + 0.12, y + 0.04, 2.66, 0.28, head, { size: 11, bold: true, color: "accent1" }),
        text(x + 0.12, y + 0.36, 2.66, h - 0.4, body, { size: 9.4, color: "text1" }),
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
slides.push({
  layout: "content", section: "Trust", title: "Security you can verify",
  notes:
    "Security and compliance is thirty percent of the score, so we made it checkable. Permission tiers are enforced in the domain layer, not just the screens. " +
    "Only a human parent with a fresh MFA proof, bound to that payment, can approve; the AI has no approve, cancel or limit permission. On the right, the live audit log says PASS, and one edited row makes it fail.",
  elements: [
    ...tiers.flatMap(([lead, rest, fill, color], i) => {
      const y = 1.4 + i * 0.52;
      return [
        rect(0.5, y, 4.4, 0.44, fill, { round: 0.06 }),
        text(0.65, y, 4.15, 0.44, [{ text: lead, bold: true }, { text: rest }], { size: 14, color, valign: "middle" }),
      ];
    }),
    ...(() => {
      const audit = liveShot("live-05-audit-verify.png", 5.1, 1.4, 4.4, "The live audit log: Verify the hash chain says PASS");
      return [
        ...audit.els,
        text(5.1, 1.4 + audit.h + 0.14, 4.4, 0.45, `Live, ${LIVE_SITE}, 19 Oct 2026: Verify the hash chain gives PASS on 40 events.`, { size: 10.5, color: "text2" }),
        card(5.1, 3.35, 4.4, 0.85),
        text(5.25, 3.4, 4.1, 0.75, [{ text: "Tamper test: ", bold: true }, { text: "edit one audit row behind the app's back and Verify fails at that event; restore it and Verify passes." }], { size: 11, color: "text1", valign: "middle" }),
        card(5.1, 4.3, 4.4, 0.85),
        text(5.25, 4.35, 4.1, 0.75, [{ text: "Also: ", bold: true }, { text: "each payment's compliance report carries a hash your browser can recompute. Every threat has a test: docs/SECURITY.md." }], { size: 11, color: "text1", valign: "middle" }),
      ];
    })(),
    text(0.5, 5.32, 9, 0.22, "Raw logs: submission/evidence/.", { size: 10, color: "text2" }),
  ],
});

// 11 --------------------------------------------------------------------------------------------
slides.push({
  layout: "content", section: "Trust", title: "Honest by design",
  notes:
    "Honesty is a feature. A banner on every screen and a sandbox header on every response say this is a sandbox. Any rule not checked against an official source carries a Not verified badge and the line: indicative, confirm with your AD bank. A payment's compliance report is sealed with a hash that the browser recomputes.",
  elements: [
    text(0.5, 1.2, 9, 0.4, "Every simulated part is labelled. Every unverified rule carries a badge.", { size: 16, bold: true, color: "text1", valign: "middle" }),
    ...shot("15-sandbox-admin.png", 0.58, 1.78, 4.0, 3.12, "Sandbox screen listing what is simulated"),
    ...shot("20-compliance-report.png", 5.42, 1.78, 4.0, 3.12, "Compliance report whose hash verifies in the browser"),
    text(0.5, 5.02, 4.16, 0.3, "Sandbox screen: what is simulated, how to test it", { size: 11, color: "text2" }),
    text(5.34, 5.02, 4.16, 0.3, "Compliance report: the hash verifies in the browser", { size: 11, color: "text2" }),
  ],
});

// 12 --------------------------------------------------------------------------------------------
// Every figure here is sourced (see docs/BUSINESS_CASE.md) or is plain arithmetic on a sourced figure.
const market = [
  ["USD 881.7m", "sent through Bangladeshi banks for overseas education in FY2025-26: a record, up 32% in a year. Bangladesh Bank data, via The Observer, 24 Jul 2026."],
  ["6.4%", "average cost of sending USD 200 worldwide, Q3 2025, against a 3% goal (World Bank). Small remittances, not tuition: context only."],
  ["USD 8.8m", "a year stays with families for each 1 point of cost taken off that volume. Our arithmetic (1% of 881.7m), not a forecast."],
];
const gains = [
  ["Family", "Lower true cost, a safe deadline, one plan."],
  ["Bank", "Documents checked and risk-routed before a reviewer looks."],
  ["University", "Fewer short or unmatched payments."],
];
slides.push({
  layout: "content", section: "Close", title: "Why it can work",
  notes:
    "Bangladesh Bank data show 881.7 million dollars sent through banks for overseas education last year, a record, up 32 percent. " +
    "If a comparison took one percentage point off that volume, families would keep about 8.8 million dollars: our arithmetic, not a forecast. " +
    "We have no partner, pilot or real users yet; these are numbers to test.",
  elements: [
    ...market.flatMap(([num, body], i) => {
      const y = 1.3 + i * 1.28;
      return [
        card(0.5, y, 5.3, 1.18),
        text(0.65, y + 0.05, 1.95, 1.08, num, { size: 21, bold: true, font: "+mj-lt", color: "accent1", valign: "middle" }),
        text(2.65, y + 0.05, 3.05, 1.08, body, { size: 11, color: "text1", valign: "middle" }),
      ];
    }),
    card(6.0, 1.3, 3.5, 3.7),
    text(6.2, 1.38, 3.1, 0.4, "Who gains", { size: 16, bold: true, color: "accent1", valign: "middle" }),
    ...gains.flatMap(([who, what], i) => [
      text(6.2, 1.85 + i * 0.62, 3.1, 0.58,
        [{ text: who + ": ", bold: true }, { text: what }], { size: 12, color: "text1", valign: "middle" }),
    ]),
    text(6.2, 3.75, 3.1, 0.3, "Who could pay (to test)", { size: 14, bold: true, color: "accent1", valign: "middle" }),
    text(6.2, 4.05, 3.1, 0.9,
      "A partner bank pays a small service fee per assisted payment. At 0.2% of the volume, a 5% share is about USD 88,000 a year: modest, and a number to test.",
      { size: 11, color: "text1" }),
    text(0.5, 5.32, 9, 0.22, "Illustrations, not forecasts. No partner, no pilot, no real users yet. Sources and sums: docs/BUSINESS_CASE.md",
      { size: 10, color: "text2" }),
    text(0.5, 5.06, 9, 0.24, "Volume is real (Bangladesh Bank, via The Observer). Rates, fees, city costs and the 8.8m figure are our arithmetic or invented for the sandbox.", { size: 9.5, color: "text2" }),
  ],
});

// 13 --------------------------------------------------------------------------------------------
const next = [
  ["Verified rules", "Four study-abroad rules now rest on Bangladesh Bank's circular. Verify the rest."],
  ["A real AD bank partner", "Real quotes, real KYC, and regulator-ready reports from the audit log."],
  ["Credit building", "Topic C scope we have not built: help a student build a credit history abroad."],
  ["A real chain", "Today the escrow runs on a simulated chain, with no network. Next: a permissioned chain and a bank-issued token."],
];
slides.push({
  layout: "closing", section: "Close", title: "What comes next",
  notes:
    "Next: replace placeholder rules with official Bangladesh Bank sources, partner with an authorised dealer bank for real quotes and KYC, and move the escrow from our simulated chain to a permissioned one. Credit building is in the brief and not built, and we would rather say so. To close: the engine calculates, the AI explains, the human approves, and every step is logged. Thank you.",
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
    text(0.5, 4.25, 9, 0.55, "Clear costs. Human control.", { size: 24, bold: true, font: "+mj-lt", color: "accent2", valign: "middle" }),
    text(0.5, 4.85, 9, 0.35, `${TEAM}  ·  ${REPO}  ·  Sandbox: no real money moves`, { size: 12, color: "accent5" }),
  ],
});


// ---------------------------------------------------------------------------------------------
// Added slides 14 to 20 (they are moved into place by ORDER below). Live pictures: 19 Oct 2026.
// ---------------------------------------------------------------------------------------------
const LIVE = "studyroute.bot-keep.xyz";

// 14: live comparison ----------------------------------------------------------------------------
{
  const quotes = liveShot("live-01-compare-quotes.png", 0.5, 1.35, 5.7, "The live site ranking three providers for GBP 10,000 by true total cost");
  const costs = [["B", 1.58, "accent1", "BDT 25,300"], ["C", 1.63, "accent3", "BDT 26,100"], ["A", 2.16, "accent4", "BDT 34,500"]];
  slides.push({
    layout: "content", section: "The solution", title: "Live: comparing providers",
    notes:
      "This is the public site, studyroute dot bot-keep dot xyz, opened on the 19th: ten thousand pounds of UK tuition. " +
      "The ranking is the one our test T01 asserts: Provider B at 1.58 percent, Provider C at 1.63 with a warning that the university would be 35 pounds short, Provider A at 2.16. " +
      "The engine calculates; the screen only shows it.",
    elements: [
      ...quotes.els,
      text(0.5, 1.35 + quotes.h + 0.14, 5.7, 0.5, `${LIVE}, GBP 10,000 UK tuition, run on 19 Oct 2026. Synthetic rates and fees.`, { size: 10, color: "text2" }),
      text(6.5, 1.35, 3.0, 0.5, "True total cost, as a share of the amount", { size: 13, bold: true, color: "text1" }),
      ...hbars({
        x: 6.5, y: 1.95, w: 3.0, labelW: 0.4, valueW: 1.0, max: 2.4, rowH: 0.62, barH: 0.3, size: 13,
        rows: costs.map(([name, value, fill, bdt]) => ({ label: name, parts: [{ value, fill, text: `${value.toFixed(2)}%` }] })),
      }),
      text(6.5, 3.95, 3.0, 0.9,
        [{ text: "C looks nearly as cheap, ", bold: true }, { text: "but it is quoted as SHA: the university would receive GBP 35 less than the invoice." }],
        { size: 12, color: "text1" }),
      text(6.5, 4.85, 3.0, 0.4, "Same figures as test T01.", { size: 10, color: "text2" }),
    ],
  });
}

// 15: live assistant -----------------------------------------------------------------------------
{
  const chat = liveShot("live-03-assistant-readback.png", 0.5, 1.35, 3.2, "The live assistant reading a request back before it plans");
  const planner = liveShot("live-04-dashboard-planner.png", 3.95, 1.35, 2.85, "The live deadline planner working back from the due date");
  const steps = [
    ["1  The reader proposes", "It marks the amount, currency and date. Plain code turns them into values."],
    ["2  You read it back", "Mandatory: say yes, or tell it what to change."],
    ["3  Only then, a plan", "From engine facts. Only you can approve, with a fresh MFA code."],
  ];
  slides.push({
    layout: "content", section: "The solution", title: "Live: one sentence, read back",
    notes:
      "On the live site the parent types one sentence. The trained reader only proposes; plain code turns the words into values; and the assistant must read them back before it plans. " +
      "Only after a yes does it plan. Beside it, the deadline planner works backwards: send by 22 October. The assistant cannot approve; only the parent can, with a fresh MFA code.",
    elements: [
      ...chat.els,
      text(0.5, 1.35 + chat.h + 0.14, 3.2, 0.3, `Live, 19 Oct 2026: the assistant panel`, { size: 10, color: "text2" }),
      ...planner.els,
      text(3.95, 1.35 + planner.h + 0.14, 2.85, 0.4, "Live deadline planner: due 1 Nov, send by 22 Oct, two calendars.", { size: 10, color: "text2" }),
      ...steps.flatMap(([head, body], i) => {
        const y = 1.35 + i * 1.2;
        return [
          card(7.1, y, 2.4, 1.1),
          rect(7.1, y, 0.07, 1.1, i === 1 ? "accent2" : "accent1"),
          text(7.28, y + 0.06, 2.16, 0.3, head, { size: 12, bold: true, color: "text1", valign: "middle" }),
          text(7.28, y + 0.38, 2.16, 0.7, body, { size: 10, color: "text2" }),
        ];
      }),
      text(7.1, 4.98, 2.4, 0.4, "The assistant cannot approve, submit or cancel.", { size: 10, bold: true, color: "accent3" }),
    ],
  });
}

// 16: models against baselines, as graphs ---------------------------------------------------------
slides.push({
  layout: "content", section: "Trust", title: "Models against baselines",
  notes:
    "The same numbers as a graph. Left: the trained reader against our old rules on 113 messages written after it was frozen. " +
    `Top right: the risk router's top one percent holds ${pc(riskOrder.found_in_top_1_percent)} of flagged payments; random order finds ${pc(riskRandom.found_in_top_1_percent)}. ` +
    `Bottom right: the dialogue policy cut wrong plans from ${pc(rlBefore.wrong_plan)} to ${pc(rlLearned.wrong_plan)} on simulated parents. Small samples, and as a plain yes or no the router is modest.`,
  elements: [
    card(0.5, 1.35, 5.3, 3.45),
    text(0.7, 1.42, 4.9, 0.4, "Reader on 113 frozen messages (higher is better)", { size: 13, bold: true, color: "text1", valign: "middle" }),
    ...hbars({
      x: 0.7, y: 1.95, w: 4.9, labelW: 1.55, valueW: 0.6, max: 100, rowH: 0.72, barH: 0.26, size: 12,
      rows: [
        ["Right intent", blind.rules.routing_accuracy, blind.agent.routing_accuracy],
        ["Plan read exactly", blind.rules.task_success, blind.agent.task_success],
        ["Attacks blocked", blind.rules.attack_blocked, blind.agent.attack_blocked],
      ].map(([label, rules, agent]) => ({
        label,
        parts: [{ value: 100 * rules, fill: "accent5", text: pc(rules) }, { value: 100 * agent, fill: "accent1", text: pc(agent) }],
      })),
    }),
    ...legend(0.7, 4.2, [["Old rules", "accent5"], ["Trained reader", "accent1"]]),
    card(6.0, 1.35, 3.5, 1.6),
    text(6.15, 1.4, 3.2, 0.5, "Router: flagged payments found in its top 1%", { size: 12, bold: true, color: "text1", valign: "middle" }),
    ...hbars({
      x: 6.15, y: 1.95, w: 3.2, labelW: 0.95, valueW: 0.6, max: 100, rowH: 0.45, barH: 0.26, size: 11,
      rows: [
        { label: "Random", parts: [{ value: 100 * riskRandom.found_in_top_1_percent, fill: "accent5", text: pc(riskRandom.found_in_top_1_percent) }] },
        { label: "Router", parts: [{ value: 100 * riskOrder.found_in_top_1_percent, fill: "accent1", text: pc(riskOrder.found_in_top_1_percent) }] },
      ],
    }),
    card(6.0, 3.1, 3.5, 1.7),
    text(6.15, 3.15, 3.2, 0.5, "Dialogue policy: wrong plans (lower is better)", { size: 12, bold: true, color: "text1", valign: "middle" }),
    ...hbars({
      x: 6.15, y: 3.7, w: 3.2, labelW: 0.95, valueW: 0.6, max: 4, rowH: 0.45, barH: 0.26, size: 11,
      rows: [
        { label: "Before", parts: [{ value: 100 * rlBefore.wrong_plan, fill: "accent5", text: pc(rlBefore.wrong_plan) }] },
        { label: "Learned", parts: [{ value: 100 * rlLearned.wrong_plan, fill: "accent1", text: pc(rlLearned.wrong_plan) }] },
      ],
    }),
    text(6.15, 4.55, 3.2, 0.25, `${rlLearned.turns.toFixed(2)} questions on average, up from ${rlBefore.turns.toFixed(2)}`, { size: 9, color: "text2" }),
    text(0.5, 4.95, 9, 0.5, "Small samples; simulated parents; synthetic data. As a plain yes or no the router is modest: flagging nothing is already 99.8% accurate, so we show how it orders payments.",
      { size: 10.5, color: "text2" }),
  ],
});

// 17: tests --------------------------------------------------------------------------------------
{
  const ci = liveShot("live-09-github-ci.png", 5.55, 1.35, 3.95, "GitHub Actions: all six CI jobs green on the latest commit");
  const tiles = [
    ["1,679", "backend tests (1,678 pass, 1 skipped)"], ["463", "web tests"],
    ["24", "browser tests"], ["314", "security probe records (308 PASS, 6 INFO)"],
    ["24 of 24", "blueprint scenarios mapped to tests"], ["6 of 6", "CI jobs green on GitHub"],
  ];
  slides.push({
    layout: "content", section: "Trust", title: "Every test we ran",
    notes:
      "Everything we ran: 1,679 backend tests, one skipped on Windows; 463 web tests; 24 browser tests; all 24 scenarios mapped; 314 security probe records. " +
      "On the right is GitHub's own page for our latest commit: all six CI jobs green. These are our own tests; a fresh clone runs 1,672 of 1,673, and no outside party has tested it.",
    elements: [
      ...tiles.flatMap(([num, label], i) => {
        const x = 0.5 + (i % 2) * 2.4;
        const y = 1.35 + Math.floor(i / 2) * 1.15;
        return [
          card(x, y, 2.3, 1.05),
          text(x + 0.12, y + 0.03, 2.06, 0.5, num, { size: 24, bold: true, font: "+mj-lt", color: "accent1", valign: "middle" }),
          text(x + 0.12, y + 0.55, 2.06, 0.46, label, { size: 10.5, color: "text2" }),
        ];
      }),
      ...ci.els,
      text(5.55, 1.35 + ci.h + 0.14, 3.95, 0.6, "GitHub Actions, latest commit: backend, web, contracts, secret-scan, dependency-audit and docker all green.", { size: 10, color: "text2" }),
      text(0.5, 4.95, 9, 0.5, "Our own tests. A fresh clone runs 1,672 of 1,673 (one module needs an excluded fixture). No independent test yet.", { size: 11, color: "text2" }),
    ],
  });
}

// 18: attack families and the man-in-the-middle test -----------------------------------------------
{
  const families = [
    ["Access control, injection", 146, "146"], ["Browser, CSP, XSS", 48, "48"], ["Leak canaries (+2 info)", 50, "50"],
    ["Hostile assistant prompts", 42, "42"], ["Man-in-the-middle (+4 info)", 14, "14"], ["Login and MFA guessing", 8, "8"],
  ];
  slides.push({
    layout: "content", section: "Trust", title: "Attacking our own app",
    notes:
      "We attacked our own application with six tools: access control, browser and XSS, planted secrets, hostile prompts, man-in-the-middle and replay, and login guessing. 314 records, all pass or informational. " +
      "The man-in-the-middle test is the honest one: altered approvals, swapped MFA proofs, a stolen token and replayed webhooks were refused. " +
      "But on plain HTTP a listener reads the password and token, and a stolen token can cancel a draft. We do not call that safe.",
    elements: [
      card(0.5, 1.35, 5.2, 3.5),
      text(0.7, 1.42, 4.8, 0.4, "Recorded checks by tool (all pass)", { size: 13, bold: true, color: "text1", valign: "middle" }),
      ...hbars({
        x: 0.7, y: 1.9, w: 4.8, labelW: 2.15, valueW: 0.55, max: 146, rowH: 0.43, barH: 0.24, size: 11,
        rows: families.map(([label, value, shown]) => ({ label, parts: [{ value, fill: "accent1", text: shown }] })),
      }),
      text(0.7, 4.5, 4.8, 0.3, "314 records: 308 PASS, 6 INFO. Team-run lab results; not 314 different attacks.", { size: 10, color: "text2" }),
      card(5.9, 1.35, 3.6, 3.5),
      text(6.05, 1.42, 3.3, 0.4, "The man-in-the-middle test", { size: 13, bold: true, color: "text1", valign: "middle" }),
      text(6.05, 1.85, 3.3, 0.3, "Held (14 of 14)", { size: 12, bold: true, color: "accent6" }),
      text(6.05, 2.15, 3.3, 1.4,
        bullets(["Altered or redirected approval: refused", "Stripped or swapped MFA proof: refused", "Stolen token cannot approve or allowlist", "Webhook tamper and replay: refused"]),
        { size: 10.5, color: "text1", paraAfter: 2 }),
      text(6.05, 3.5, 3.3, 0.3, "Did not hold", { size: 12, bold: true, color: "accent3" }),
      text(6.05, 3.8, 3.3, 1.0,
        bullets(["Plain HTTP: a listener reads the password and token", "A stolen token reads payments and cancels a draft for 15 minutes"]),
        { size: 10.5, color: "text1", paraAfter: 2 }),
      text(0.5, 4.95, 9, 0.3, "Raw logs and hashes: submission/evidence/security_2026-10-18/ and the security self-assessment, sections 13 and 14.", { size: 10, color: "text2" }),
    ],
  });
}

// 19: the security problems ----------------------------------------------------------------------
{
  const head = ["Problem found", "Status", "What we did, or still need"].map((t) => ({ text: t, bold: true, color: "background1", fill: "text1" }));
  const status = (label, color) => ({ text: label, bold: true, color });
  const rows = [
    ["Plain HTTP exposes the password and token", status("Mitigated", "accent1"), "The public site answers over HTTPS with an HSTS header (seen 19 Oct). The local demo is HTTP by design. Not independently tested."],
    ["A stolen token reads payments, cancels a draft (15 min)", status("Open", "accent3"), "Approval still needs a fresh MFA proof bound to the payment. Cancel rights are under review."],
    ["Account names guessable after repeated failures", status("Fixed", "accent6"), "Uniform lockout and failure tracking, with tests."],
    ["Model runtime phoned a public telemetry host", status("Fixed", "accent6"), "Switched off; a new capture found no packet to a public address."],
    ["Document text, with a planted passport, was readable", status("Partly", "accent4"), "New rows use AES-256-GCM. Old rows, names and file names stay readable."],
    ["Nine high advisories in development tools", status("Open", "accent3"), "Dev tools only; upgrade deferred. Not a clean bill of health."],
    ["No independent penetration test; simulated chain", status("Open", "accent3"), "Every attack tool was written by the team. The chain is a simulation."],
  ].map(([problem, st, note], i) => [
    { text: problem, bold: true, fill: i % 2 === 0 ? "background2" : undefined }, { ...st, fill: i % 2 === 0 ? "background2" : undefined }, { text: note, fill: i % 2 === 0 ? "background2" : undefined },
  ]);
  slides.push({
    layout: "content", section: "Trust", title: "Security problems we found",
    notes:
      "We list our security problems because hiding them would cost more. On plain HTTP a listener reads the password and token; the public site uses HTTPS with HSTS, but nobody else has tested that. " +
      "A stolen token can read payments and cancel a draft, not approve. We fixed account guessing and a telemetry leak. Old document rows stay readable, development tools carry advisories, and no outside penetration test has been done.",
    elements: [
      { type: "table", x: 0.5, y: 1.3, colW: [3.1, 0.95, 4.95], rowH: 0.45, size: 10, rows: [head, ...rows] },
      text(0.5, 5.0, 9, 0.3, "Source: security self-assessment, edition 1.2, sections 13 and 14: every record, the raw-log hashes and what each fix did and did not show.", { size: 10, color: "text2" }),
    ],
  });
}

// 20: the AI risk score and the human decision ----------------------------------------------------
{
  const card1 = image("43-risk-score-card.png", 0.5, 1.35, 5.6, 1.89, "The parent's view: AI risk score 99 out of 100 with the four factors");
  const card2 = image("44-review-decision.png", 0.5, 3.72, 2.7, 1.43, "The bank reviewer's decision: yes, ask for more or no, signed with MFA");
  const steps = [
    ["1  Score", "A small neural network rates each payment 0 to 100 from four factors: amount, frequency, timeline and person."],
    ["2  Route", "Low: no warning, nobody waits. Medium or high: a warning, and a person at the bank looks."],
    ["3  Decide", "The reviewer answers yes, ask for more or no, signed with a fresh MFA code. The parent still authorizes."],
    ["4  Limits", `It never clears, declines or approves. Its top 1% holds ${pc(riskOrder.found_in_top_1_percent)} of flagged payments (random: ${pc(riskRandom.found_in_top_1_percent)}). Trained on public synthetic data.`],
  ];
  slides.push({
    layout: "content", section: "Trust", title: "Risk score, human decision",
    notes:
      "Every payment gets an AI risk score out of 100 from four factors: amount, frequency, timeline and person. Low means no warning and nobody waits. " +
      "Medium or high shows a warning and sends the payment to a person at the bank, who answers yes, ask for more, or no, with MFA. The score never approves; the parent still authorizes.",
    elements: [
      rect(0.42, 1.27, 5.76, 2.05, "background1", { round: 0.06, line: "accent5", shadow: true }),
      card1,
      text(0.5, 3.36, 5.6, 0.3, "The parent's view: score 99 of 100, medium risk, the four factors and a warning.", { size: 10, color: "text2" }),
      rect(0.42, 3.64, 2.86, 1.59, "background1", { round: 0.06, line: "accent5", shadow: true }),
      card2,
      text(3.45, 3.8, 2.65, 1.3, "The bank reviewer's view: three answers, signed with a fresh MFA code. The AI cannot choose for them.", { size: 10, color: "text2" }),
      ...steps.flatMap(([head, body], i) => {
        const y = 1.35 + i * 0.97;
        return [
          card(6.4, y, 3.1, 0.89),
          rect(6.4, y, 0.07, 0.89, i === 3 ? "accent3" : "accent1"),
          text(6.58, y + 0.04, 2.85, 0.26, head, { size: 11.5, bold: true, color: "text1", valign: "middle" }),
          text(6.58, y + 0.3, 2.85, 0.58, body, { size: 9, color: "text2" }),
        ];
      }),
      text(0.5, 5.3, 9, 0.25, "Local sandbox screenshots, synthetic data. Indicative. Confirm with your AD bank.", { size: 9, color: "text2" }),
    ],
  });
}

// Final order: the live and chart slides sit beside the slides they support.
const ORDER = [1, 2, 3, 4, 5, 14, 6, 15, 8, 9, 16, 20, 7, 17, 10, 18, 19, 11, 12, 13];
if (slides.length !== ORDER.length) throw new Error(`Expected ${ORDER.length} slides, found ${slides.length}.`);
slides.splice(0, slides.length, ...ORDER.map((n) => slides[n - 1]));

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
