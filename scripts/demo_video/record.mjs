#!/usr/bin/env node
/**
 * Record the scenes of the demo video (submission/VIDEO_SCRIPT.md) from a LOOPBACK sandbox, one clip of frames per scene.
 *
 *   python scripts/demo_video/make_video.py          # the whole job: fresh data, servers, this recorder, the assembler
 *   node scripts/demo_video/record.mjs --base http://127.0.0.1:8190 --out dist/demo-video/frames --scenes dist/demo-video/scenes.json
 *
 * It signs in as the three demo accounts (parent, bank reviewer, student) in three separate browser sessions, does what the script's
 * "What to do" column says at human speed, and saves the frames Chrome paints (with a drawn cursor, click ripples and highlights)
 * plus a manifest of when each frame was shown. Take 1 (scenes 0 to 3) and Take 2 (scenes 4 to 9) follow the script; the bank's
 * payment is staged between them with `python -m app.scripts.review_demo --leave-open`.
 *
 * Every scene is paced to the narration: `at(t)` waits until t seconds into the scene, and t is where the narrator reaches the
 * sentence that describes what happens next (the timing model is the one assemble.py uses for the guide video).
 *
 * Sandbox only: the base URL must be 127.0.0.1, localhost or [::1], never a deployment. Needs the web dependencies (puppeteer-core),
 * Google Chrome, a running API plus the built UI, and fresh demo data (make_video.py arranges all of that).
 * --dry plays the scenes without saving frames, skips the padding and takes a screenshot at every cue, to check the choreography.
 * --only 4,5,6 plays just those scenes (scenes 4 and later need the staged payment, which is made when any of them is included).
 */
import cp from "node:child_process";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const require = createRequire(path.join(ROOT, "web", "package.json"));
const puppeteer = require("puppeteer-core");

const arg = (name, fallback) => {
  const at = process.argv.indexOf(`--${name}`);
  return at === -1 ? fallback : process.argv[at + 1];
};
const BASE = arg("base", "http://127.0.0.1:8190").replace(/\/$/, "");
const OUT = path.resolve(arg("out", path.join(ROOT, "dist", "demo-video", "frames")));
const SCENES_FILE = path.resolve(arg("scenes", path.join(ROOT, "dist", "demo-video", "scenes.json")));
const PYTHON = arg("python", path.join(ROOT, "backend", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python"));
const CHROME = arg("chrome", process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe");
const DRY = process.argv.includes("--dry");
const ONLY = arg("only", "") ? arg("only", "").split(",").map(Number) : null;
// 1280 x 680 CSS pixels at 1.5x is 1920 x 1020 on screen; the assembler adds a 60 px bar to make 1920 x 1080.
const VIEW = { width: 1280, height: 680, deviceScaleFactor: 1.5 };

if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(BASE).hostname)) {
  throw new Error("Only a loopback sandbox may be recorded; never point this at a deployment.");
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const scenes = JSON.parse(fs.readFileSync(SCENES_FILE, "utf8")).scenes;
const WINDOW = Object.fromEntries(scenes.map((s) => [s.number, s.window]));
let seed = 7; // the idle drift of the pointer is the same on every take
const rand = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;

// ---------------------------------------------------------------------------------------------------------------------
// Code that runs inside the page. Everything is built with the DOM and CSSOM, never an inline style attribute or a <style>
// element, so it works under the application's strict content-security policy.
// ---------------------------------------------------------------------------------------------------------------------
function overlayInPage() {
  if (window.__demo && document.body.contains(window.__demoRoot)) return;
  const NS = "http://www.w3.org/2000/svg";
  const put = (el, props) => { for (const [k, v] of Object.entries(props)) el.style.setProperty(k, v); return el; };
  const root = put(document.createElement("div"), {
    position: "fixed", left: "0", top: "0", width: "100vw", height: "100vh", "pointer-events": "none", "z-index": "2147483647",
  });
  const cursor = document.createElementNS(NS, "svg");
  for (const [k, v] of [["width", "30"], ["height", "30"], ["viewBox", "0 0 30 30"]]) cursor.setAttribute(k, v);
  const arrow = document.createElementNS(NS, "path");
  for (const [k, v] of [["d", "M4 3 L4 23.5 L9.4 18.6 L13 26.4 L16.6 24.9 L13 17.2 L20.6 17.2 Z"], ["fill", "#111827"], ["stroke", "#ffffff"], ["stroke-width", "1.7"], ["stroke-linejoin", "round"]]) arrow.setAttribute(k, v);
  cursor.appendChild(arrow);
  put(cursor, { position: "absolute", left: "0", top: "0", transform: "translate(-100px,-100px)", filter: "drop-shadow(0 2px 3px rgba(0,0,0,.4))" });
  root.appendChild(cursor);
  document.body.appendChild(root);
  let flip = 0;
  window.__demoRoot = root;
  window.__demo = {
    move(x, y) { cursor.style.setProperty("transform", `translate(${x}px, ${y}px)`); },
    pulse(x, y) { flip = 1 - flip; cursor.style.setProperty("transform", `translate(${x + flip * 0.02}px, ${y}px)`); },
    ripple(x, y) {
      const ring = put(document.createElement("div"), {
        position: "absolute", left: `${x - 24}px`, top: `${y - 24}px`, width: "48px", height: "48px", "border-radius": "50%",
        background: "rgba(244,185,66,.40)", border: "2px solid rgba(244,185,66,.95)", "box-sizing": "border-box",
      });
      root.appendChild(ring);
      const a = ring.animate([{ transform: "scale(.25)", opacity: 0.95 }, { transform: "scale(1.45)", opacity: 0 }], { duration: 540, easing: "ease-out" });
      a.onfinish = () => ring.remove();
    },
    spot(x, y, w, h, ms) {
      const box = put(document.createElement("div"), {
        position: "absolute", left: `${x - 7}px`, top: `${y - 7}px`, width: `${w + 14}px`, height: `${h + 14}px`, "border-radius": "11px",
        border: "3px solid #F4B942", "box-shadow": "0 0 0 5px rgba(244,185,66,.22)", "box-sizing": "border-box",
      });
      root.appendChild(box);
      const a = box.animate([{ opacity: 0 }, { opacity: 1, offset: 0.12 }, { opacity: 1, offset: 0.86 }, { opacity: 0 }], { duration: ms });
      a.onfinish = () => box.remove();
    },
  };
}

// Find a visible element by its text (or aria-label / placeholder) and return where it is on screen. mode "scroll" also eases it
// into view. The smallest matching element wins, so a link's label is preferred to the whole row that contains it (spec.dom keeps
// document order instead, for lists). An element in a fixed or sticky bar never needs scrolling.
function locateInPage(spec, mode) {
  const norm = (s) => (s || "").replace(/[\u2018\u2019]/g, "'").replace(/\s+/g, " ").trim().toLowerCase();
  const want = spec.text == null ? null : norm(spec.text);
  const selector = spec.sel || 'button, a, [role="tab"], [role="menuitem"], tr, label, input, textarea, select, summary, h1, h2, h3, h4, legend, section, p, span, td, th, li, dt, dd, div';
  const found = [];
  for (const node of document.querySelectorAll(selector)) {
    const r = node.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const cs = getComputedStyle(node);
    if (cs.visibility === "hidden" || cs.display === "none") continue;
    if (spec.xMax != null && r.left > spec.xMax) continue;
    if (spec.xMin != null && r.left < spec.xMin) continue;
    if (spec.inside && !node.closest(spec.inside)) continue;
    if (want !== null) {
      const t = norm(node.innerText) || norm(node.value) || norm(node.getAttribute("aria-label")) || norm(node.getAttribute("placeholder"));
      if (spec.exact ? t !== want : !t.includes(want)) continue;
    }
    found.push(node);
  }
  if (!found.length) return null;
  if (!spec.dom) found.sort((a, b) => a.querySelectorAll("*").length - b.querySelectorAll("*").length);
  let el = found[spec.nth || 0];
  if (!el) return null;
  for (let i = 0; i < (spec.up || 0) && el.parentElement; i++) el = el.parentElement;
  let pinned = false;
  for (let e = el; e && e !== document.body; e = e.parentElement) {
    const p = getComputedStyle(e).position;
    if (p === "fixed" || p === "sticky") pinned = true;
  }
  if (mode === "scroll" && !pinned) {
    el.style.setProperty("scroll-margin-top", "112px");
    el.style.setProperty("scroll-margin-bottom", "40px");
    el.scrollIntoView({ block: spec.block || "center", behavior: "smooth" });
  }
  const r = el.getBoundingClientRect();
  // Is the top of it clear of the sticky header? Something in the amber banner above the header needs no scrolling.
  const probe = document.elementFromPoint(Math.min(Math.max(r.left + r.width / 2, 1), innerWidth - 1), Math.min(Math.max(r.top + 2, 1), innerHeight - 1));
  const clear = !!probe && el.contains(probe);
  const fits = (clear ? r.top >= 0 : r.top >= 100) && r.bottom <= innerHeight - 6;
  const tall = r.height > innerHeight * 0.55 && r.top < innerHeight * 0.45 && r.bottom > innerHeight * 0.45;
  return { x: r.left, y: r.top, w: r.width, h: r.height, inView: pinned || fits || tall };
}

function scrollInPage(dy, ms) {
  let scroller = null;
  for (let e = document.querySelector("main#main"); e && !scroller; e = e.parentElement) {
    const cs = getComputedStyle(e);
    if (/(auto|scroll)/.test(cs.overflowY) && e.scrollHeight > e.clientHeight + 4) scroller = e;
  }
  scroller = scroller || document.scrollingElement;
  scroller.style.setProperty("scroll-behavior", "auto");
  const from = scroller.scrollTop;
  const to = Math.max(0, Math.min(scroller.scrollHeight - scroller.clientHeight, from + dy));
  return new Promise((resolve) => {
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / ms);
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      scroller.scrollTop = from + (to - from) * e;
      if (k < 1) requestAnimationFrame(step);
      else resolve({ from, to: scroller.scrollTop });
    };
    requestAnimationFrame(step);
  });
}

// ---------------------------------------------------------------------------------------------------------------------
// One browser session = one person. "cam" is that person's page plus the things a viewer needs to follow it.
// ---------------------------------------------------------------------------------------------------------------------
class Cam {
  constructor(page, name) {
    this.page = page;
    this.name = name;
    this.cur = { x: 900, y: 160 };
    this.problems = [];
    page.on("pageerror", (e) => this.problems.push(`${name} pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (/Content Security Policy|violates/i.test(m.text())) this.problems.push(`${name} csp: ${m.text().slice(0, 200)}`);
    });
  }

  async init() {
    await this.page.evaluate(overlayInPage);
    await this.page.evaluate((x, y) => window.__demo.move(x, y), this.cur.x, this.cur.y);
  }

  async ensure() {
    const alive = await this.page.evaluate(() => !!(window.__demo && document.body.contains(window.__demoRoot)));
    if (!alive) await this.init();
  }

  async reload() {
    await this.page.reload({ waitUntil: "networkidle0" });
    await sleep(700);
    await this.init();
  }

  async rect(spec, { scroll = true, timeout = 12000 } = {}) {
    const deadline = Date.now() + timeout;
    let scrolls = 0;
    for (;;) {
      await this.ensure();
      const r = await this.page.evaluate(locateInPage, spec, "rect");
      if (r) {
        if (scroll && !r.inView && scrolls < 3) {
          scrolls += 1;
          autoScrolls.push({ at: Date.now() / 1000, target: JSON.stringify(spec).slice(0, 90) });
          await this.page.evaluate(locateInPage, spec, "scroll");
          await sleep(1100);
          continue;
        }
        return r;
      }
      if (Date.now() > deadline) throw new Error(`${this.name}: not found ${JSON.stringify(spec)}`);
      await sleep(250);
    }
  }

  async waitText(text, timeout = 15000) {
    await this.page.waitForFunction((t) => document.body.innerText.includes(t), { timeout }, text);
  }

  async glide(x, y, ms = 800) {
    await this.ensure();
    const from = { ...this.cur };
    const t0 = performance.now();
    for (;;) {
      const k = Math.min(1, (performance.now() - t0) / ms);
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      const cx = from.x + (x - from.x) * e;
      const cy = from.y + (y - from.y) * e;
      await Promise.all([this.page.mouse.move(cx, cy), this.page.evaluate((a, b) => window.__demo.move(a, b), cx, cy)]);
      if (k >= 1) break;
    }
    this.cur = { x, y };
  }

  center(r, dx, dy) {
    return { x: dx == null ? r.x + r.w / 2 : r.x + dx, y: dy == null ? r.y + r.h / 2 : r.y + dy };
  }

  async point(spec, { ms = 800, dx, dy } = {}) {
    const r = await this.rect(spec);
    const c = this.center(r, dx, dy);
    await this.glide(c.x, c.y, ms);
    return r;
  }

  async click(spec, { ms = 850, dx, dy } = {}) {
    const r = await this.point(spec, { ms, dx, dy });
    await sleep(200);
    const c = this.center(r, dx, dy);
    await this.page.evaluate((a, b) => window.__demo.ripple(a, b), c.x, c.y);
    await this.page.mouse.click(c.x, c.y, { delay: 70 });
    await sleep(300);
    return r;
  }

  async type(text, delay = 60) {
    await this.page.keyboard.type(text, { delay });
  }

  async spot(spec, ms = 2400, { wait = true } = {}) {
    const r = await this.rect(spec);
    await this.page.evaluate((a, b, c, d, e) => window.__demo.spot(a, b, c, d, e), r.x, r.y, r.w, r.h, ms);
    if (wait) await sleep(ms);
    return r;
  }

  async scrollTo(spec, block = "center") {
    await this.ensure();
    const r = await this.page.evaluate(locateInPage, { ...spec, block }, "scroll");
    if (!r) throw new Error(`${this.name}: cannot scroll to ${JSON.stringify(spec)}`);
    await sleep(1150);
  }

  async scrollBy(dy, ms = 2400) {
    const moved = await this.page.evaluate(scrollInPage, dy, ms);
    if (Math.abs(moved.to - moved.from) < 1) console.log(`  warning: ${this.name} did not scroll (${dy} px asked)`);
    await sleep(120);
  }

  // Keep the picture alive while the narrator talks: the pointer drifts a few pixels, so the video never looks frozen.
  async idle(seconds) {
    const end = Date.now() + seconds * 1000;
    while (Date.now() < end) {
      const left = (end - Date.now()) / 1000;
      if (left < 0.5) { await sleep(left * 1000); break; }
      const dx = (rand() - 0.5) * 22;
      const dy = (rand() - 0.5) * 16;
      await this.glide(Math.max(40, this.cur.x + dx), Math.max(90, this.cur.y + dy), Math.min(1200, left * 900));
    }
  }
}

// ---------------------------------------------------------------------------------------------------------------------
// Capturing frames: Chrome's screencast sends a frame whenever the page repaints, each with the time it was painted.
// ---------------------------------------------------------------------------------------------------------------------
async function startCapture(page, dir) {
  const client = await page.createCDPSession();
  const frames = [];
  client.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
    const file = `f${String(frames.length).padStart(6, "0")}.jpg`;
    fs.writeFileSync(path.join(dir, file), Buffer.from(data, "base64"));
    frames.push({ file, t: metadata.timestamp });
    client.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  await client.send("Page.startScreencast", { format: "jpeg", quality: 85, maxWidth: 1920, maxHeight: 1020, everyNthFrame: 2 });
  return {
    frames,
    async stop() {
      await client.send("Page.stopScreencast").catch(() => {});
      await client.detach().catch(() => {});
    },
  };
}

const manifest = { base: BASE, viewport: VIEW, scenes: [], problems: [] };
const autoScrolls = []; // every time a lookup had to scroll its target into view: a held-up step shows here

async function scene(number, cam, body) {
  if (ONLY && !ONLY.includes(number)) return;
  const planned = WINDOW[number];
  const dir = path.join(OUT, `s${number}`);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  if (DRY) fs.mkdirSync(path.join(OUT, "dry"), { recursive: true });
  await cam.page.bringToFront();
  await cam.ensure();
  const capture = DRY ? null : await startCapture(cam.page, dir);
  const started = Date.now();
  const elapsed = () => (Date.now() - started) / 1000;
  const nudge = () => cam.page.evaluate((x, y) => window.__demo.pulse(x, y), cam.cur.x, cam.cur.y);
  const marks = [];
  const late = [];
  // Wait (with the pointer drifting) until t seconds into the scene, then note what happens next as a cue for the narrator.
  const at = async (t, label) => {
    const wait = t - elapsed();
    if (wait > 0.05) await cam.idle(wait);
    else if (wait < -0.8) late.push(`${label || "a step"}: ${(-wait).toFixed(1)} s late (due at ${t} s)`);
    if (label) {
      marks.push({ at: Date.now() / 1000, label });
      if (DRY) await cam.page.screenshot({ path: path.join(OUT, "dry", `s${number}_${String(marks.length).padStart(2, "0")}.png`) });
    }
  };
  await nudge();
  try {
    await body({ at, elapsed });
    const left = planned - elapsed();
    if (left > 0.4 && !DRY) await cam.idle(left);
  } catch (error) {
    if (!DRY) throw error;
    // A rehearsal goes on to the next scene, so one pass finds every broken step.
    await cam.page.screenshot({ path: path.join(OUT, `fail_s${number}.png`) }).catch(() => {});
    manifest.problems.push(`scene ${number}: ${error.message.split("\n")[0]}`);
    console.log(`scene ${number}: FAILED: ${error.message.split("\n")[0]}`);
  } finally {
    await nudge().catch(() => {});
    await sleep(200);
  }
  const ended = Date.now();
  if (capture) await capture.stop();
  if (DRY) await cam.page.screenshot({ path: path.join(OUT, "dry", `s${number}_end.png`) });
  const real = (ended - started) / 1000;
  manifest.scenes.push({
    number, planned, real, dir: `s${number}`, started: started / 1000, ended: ended / 1000, marks, late, frames: capture ? capture.frames : [],
  });
  console.log(`scene ${number}: ${real.toFixed(1)} s for a ${planned} s window${capture ? `, ${capture.frames.length} frames` : " (dry: the work only, no padding)"}`);
  for (const line of late) console.log(`  late: ${line}`);
  for (const s of autoScrolls.splice(0)) console.log(`  scrolled: ${s.target} at ${(s.at - started / 1000).toFixed(1)} s`);
  if (real > planned * 1.04) console.log(`  warning: scene ${number} ran ${(real - planned).toFixed(1)} s over its window; the assembler would speed it up`);
}

// ---------------------------------------------------------------------------------------------------------------------
// Signing in, and the facts the demo needs from the sandbox itself (its public demo accounts and MFA code).
// ---------------------------------------------------------------------------------------------------------------------
async function api(pathname, { method = "GET", token, body } = {}) {
  const reply = await fetch(`${BASE}/api/v1${pathname}`, {
    method,
    headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!reply.ok) throw new Error(`${method} ${pathname} -> ${reply.status} ${(await reply.text()).slice(0, 200)}`);
  return reply.json();
}

async function signIn(browser, name, email, password) {
  const page = await (await browser.createBrowserContext()).newPage();
  await page.setViewport(VIEW);
  await page.goto(`${BASE}/login/`, { waitUntil: "networkidle0" });
  await page.waitForSelector('input[type="email"]');
  await page.type('input[type="email"]', email);
  await page.type('input[type="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForSelector("main#main", { timeout: 30000 });
  await sleep(1500);
  const cam = new Cam(page, name);
  await cam.init();
  return cam;
}

function stagePayment() {
  const run = cp.spawnSync(PYTHON, ["-m", "app.scripts.review_demo", "--base-url", BASE, "--leave-open"], {
    cwd: path.join(ROOT, "backend"), encoding: "utf8", env: process.env,
  });
  const out = `${run.stdout}${run.stderr}`;
  const left = /Left waiting for the bank:\s*(pay_\w+)/.exec(out);
  if (run.status !== 0 || !left) throw new Error(`staging the bank's payment failed:\n${out.slice(-800)}`);
  console.log(`staged: ${left[1]}`);
  return left[1];
}

// ---------------------------------------------------------------------------------------------------------------------
// The scenes. The wording of each is in submission/VIDEO_SCRIPT.md; the numbers in at() come from the narration timing.
// ---------------------------------------------------------------------------------------------------------------------
const sidebar = (text) => ({ sel: "a", exact: true, xMax: 280, text });
const RISK = 'section[aria-label="AI risk score"]';
const FACTORS = 'ul[aria-label="What the score is made of"] > li';
const DIALOG = '[role="dialog"]';
const BANNER = { text: "Sandbox. Synthetic data, no real money moves", sel: "div, p, span" };

async function main() {
  const health = await (await fetch(`${BASE}/api/v1/health`)).json();
  if (health.mode !== "sandbox" || !health.demo) throw new Error("This is not a sandbox with the public demo accounts; refusing to record it.");
  const { accounts, password, mfa_code: mfa, parent_id: parentId } = health.demo;
  const email = (who) => accounts.find((a) => a.startsWith(`${who}@`));
  fs.mkdirSync(OUT, { recursive: true });

  // Off camera: the identity check is already verified, as it would be for a family that has used the sandbox before.
  const admin = await api("/auth/login", { method: "POST", body: { email: email("admin"), password } });
  await api("/kyc/mock-review", { method: "PUT", token: admin.access_token, body: { user_id: parentId, status: "VERIFIED" } });

  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: "new", defaultViewport: VIEW,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--force-color-profile=srgb", "--hide-scrollbars"],
  });
  try {
    const parent = await signIn(browser, "parent", email("parent"), password);
    await sleep(1200);
    const reviewer = await signIn(browser, "reviewer", email("admin"), password);
    await sleep(1200);
    const student = await signIn(browser, "student", email("student"), password);
    const everyone = [parent, reviewer, student];
    const enterCode = async (cam) => {
      await cam.click({ sel: `${DIALOG} input` }, { ms: 700 });
      await cam.type(mfa, 170);
      await sleep(500);
      await cam.click({ text: "Confirm", sel: "button", exact: true, inside: DIALOG }, { ms: 800 });
    };

    // Off camera: one greeting to the assistant. Its header reads "Cloud assistant" until the first reply, which is a placeholder
    // and not what this sandbox runs; with the greeting answered, the header is right when the chat opens on camera (scene 3).
    await parent.click({ text: "Ask the assistant", sel: "button" }, { ms: 500 });
    await parent.page.waitForSelector("#chat-input", { visible: true });
    await parent.click({ sel: "#chat-input" }, { ms: 400 });
    await parent.type("hello", 40);
    await parent.page.keyboard.press("Enter");
    await parent.page.waitForFunction(() => !document.body.innerText.includes("Cloud assistant"), { timeout: 30000 });
    await sleep(600);
    if (DRY) {
      fs.mkdirSync(path.join(OUT, "dry"), { recursive: true });
      await parent.page.screenshot({ path: path.join(OUT, "dry", "prewarm.png") });
    }
    await parent.click({ text: "Close", sel: "button", exact: true, inside: DIALOG }, { ms: 500 });
    await sleep(900);
    autoScrolls.length = 0;

    // ---- Take 1: the parent (scenes 0 to 3) ---------------------------------------------------------------------------
    await scene(0, parent, async ({ at }) => {
      await at(0.2, "The amber sandbox banner is on screen, and stays on every screen");
      await parent.glide(430, 215, 1400);
      await at(3.0, "The dashboard scrolls: identity check, deadline planner, recent payments");
      await parent.scrollBy(380, 3600);
      await at(8.2);
      await parent.scrollBy(-380, 1100);
      await at(9.8, "The banner again: a sandbox where nothing is real");
      await parent.spot(BANNER, 3400);
    });

    await scene(1, parent, async ({ at }) => {
      await parent.click({ sel: "#due-date" }, { ms: 900 });
      await parent.click({ sel: 'button[data-day="11/1/2026"], button[aria-label*="November 1st, 2026"]' }, { ms: 800 });
      await sleep(500);
      await at(3.6, "The deadline planner: due date 1 Nov, and the latest send date it works back to");
      await parent.spot({ text: "Latest send date", exact: true, up: 1, xMin: 300 }, 3400);
    });

    await scene(2, parent, async ({ at }) => {
      await parent.click(sidebar("Compare"), { ms: 1000 });
      await parent.rect({ text: "Get quotes", sel: "button", exact: true });
      await at(3.4, "Compare: the defaults are United Kingdom, GBP 10,000, tuition");
      await parent.click({ text: "Get quotes", sel: "button", exact: true }, { ms: 900 });
      await parent.waitText("Short by GBP 35.00", 20000);
      await sleep(500);
      await parent.scrollTo({ text: "Short by GBP 35.00", sel: "span, div, p" }, "center");
      await at(9.4, "Provider B is cheapest: 1.58 percent");
      await parent.point({ text: "1.58%", sel: "span, div, p, td" }, { ms: 900 });
      await parent.spot({ text: "1.58%", sel: "span, div, p, td" }, 2800);
      await at(13.6, "Provider C: the red 'Short by GBP 35' warning");
      await parent.point({ text: "Short by GBP 35.00", sel: "span, div, p" }, { ms: 1000 });
      await parent.spot({ text: "Short by GBP 35.00", sel: "span, div, p" }, 3600);
      await at(18.8, "The note under Provider C: the university may receive GBP 35 less than the invoice");
      await parent.spot({ text: "The university may receive GBP 35.00 less", sel: "p, div, span" }, 3800);
      await at(23.5, "The currency-drop stress test");
      await parent.scrollTo({ text: "Currency-drop stress test", sel: "h2, h3, div, span", exact: true }, "start");
      await parent.glide(700, 420, 900);
    });

    await scene(3, parent, async ({ at }) => {
      await at(0.6, "Click 'Ask the assistant' (top right)");
      await parent.click({ text: "Ask the assistant", sel: "button" }, { ms: 900 });
      await parent.page.waitForSelector("#chat-input", { visible: true });
      await at(2.4);
      await parent.click({ sel: "#chat-input" }, { ms: 700 });
      await at(3.4, "Types one sentence: I need to pay GBP 10,000 tuition to a UK university by 1 November");
      await parent.type("I need to pay GBP 10,000 tuition to a UK university by 1 November", 50);
      await sleep(350);
      await parent.page.keyboard.press("Enter");
      await parent.waitText("Before I plan your payment", 25000);
      await sleep(300);
      await at(8.8, "The read-back card: 'Before I plan your payment, please check what I understood'");
      await parent.spot({ sel: '[aria-label="Confirm what I understood"]' }, 3200);
      await at(14.6, "'Yes, plan it': the parent confirms what it understood");
      await parent.click({ text: "Yes, plan it", sel: "button", exact: true }, { ms: 900 });
      await parent.waitText("Payment plan:", 25000);
      await sleep(900);
      await at(17.4, "The payment plan card: every number comes from the engine");
      await parent.spot({ sel: '[aria-label="Payment plan"]' }, 3400);
      await at(21.4, "The assistant's note: it cannot approve, submit, cancel or change anything");
      await parent.scrollTo({ text: "I explain the engine", sel: "p, div, span" }, "start");
      await parent.spot({ text: "I explain the engine", sel: "p, div, span" }, 3600);
      await at(26.8, "Close the chat (the X)");
      await parent.click({ text: "Close", sel: "button", exact: true, inside: DIALOG }, { ms: 900 });
    });

    // ---- The bank's payment is staged now. Take 2 (scenes 4 to 9) goes straight through: its quote lasts five minutes. ---
    if (!ONLY || ONLY.some((n) => n >= 4)) stagePayment();
    const stagedAt = Date.now();

    await scene(4, parent, async ({ at }) => {
      await at(0.4, "Click Payments");
      await parent.click(sidebar("Payments"), { ms: 1000 });
      await parent.rect({ text: "8,000.00", sel: "tr" });
      await at(2.4, "The newest payment: GBP 8,000 to a university the parent has not paid before, waiting for the bank");
      await parent.spot({ text: "8,000.00", sel: "tr" }, 2000);
      await at(4.5, "Open that payment");
      await parent.click({ text: "8,000.00", sel: "tr" }, { ms: 900, dx: 150 });
      await at(5.9, "'Open the full page'");
      await parent.click({ text: "Open the full page", sel: "a, button" }, { ms: 800 });
      await parent.waitText("The bank's check", 20000);
      await sleep(300);
      await at(7.8, "The bank's check: the AI risk score card");
      await parent.scrollTo({ text: "The bank's check", sel: "h2, h3, div", exact: true }, "start");
      await parent.spot({ sel: RISK }, 3000, { wait: false });
      await at(10.4, "The score: AI risk score N out of 100");
      await parent.point({ sel: `${RISK} > p`, dom: true }, { ms: 900, dx: 120 });
      for (const [index, [t, label]] of [[12.3, "Factor 1: amount"], [13.4, "Factor 2: frequency"], [14.6, "Factor 3: timeline"], [15.8, "Factor 4: person"]].entries()) {
        await at(t, label);
        await parent.point({ sel: FACTORS, nth: index, dom: true }, { ms: 700, dx: 90 });
      }
      await at(17.4, "Medium means a warning: a person at the bank looks");
      await parent.spot({ text: "The AI rates this payment as", sel: `${RISK} p, ${RISK} div` }, 4200);
      await at(23.2, "The score never approves: the parent still needs their own MFA code");
      await parent.spot({ text: "it cannot clear, decline or approve", sel: `${RISK} p` }, 4600);
    });

    await scene(5, reviewer, async ({ at }) => {
      await at(1.0, "Click Bank review");
      await reviewer.click(sidebar("Bank review"), { ms: 1100 });
      await reviewer.rect({ text: "Open brief", sel: "a" });
      await at(3.0, "The bank review desk: one payment is waiting");
      await reviewer.spot({ text: "Open brief", sel: "tr" }, 3400);
      await at(7.3, "'Most payments never reach this desk': they take the fast lane");
      await reviewer.spot({ text: "Most payments never appear here", sel: "p" }, 4400);
      await at(12.9, "'This one did': open the brief");
      await reviewer.click({ text: "Open brief", sel: "a" }, { ms: 900 });
      await reviewer.waitText("Bank review brief", 20000);
      await sleep(500);
      await at(15.2, "The brief: the facts (payer, receiver, amount)");
      await reviewer.scrollTo({ text: "Bank review brief", sel: "h2, h3, div", exact: true }, "start");
      await reviewer.glide(700, 330, 900);
      await at(18.6, "The brief: the AI's reading, with its reasons");
      await reviewer.scrollBy(300, 3000);
      await at(22.0, "The brief: what to check");
      await reviewer.scrollBy(300, 2400);
      await at(24.7, "'I decide': Your decision");
      await reviewer.scrollTo({ text: "Your decision", sel: "legend", exact: true }, "center");
      await at(28.0, "Choose 'Yes, clear it'");
      await reviewer.click({ text: "Yes, clear it", sel: "span", exact: true }, { ms: 1000 });
      await at(30.4, "'Sign with MFA and send'");
      await reviewer.click({ text: "Sign with MFA and send", sel: "button", exact: true }, { ms: 900 });
      await reviewer.waitText("Sign this decision", 10000);
      await at(33.0, "A fresh MFA code, typed by the reviewer (246810 in the sandbox)");
      await enterCode(reviewer);
      await reviewer.waitText("Decided", 20000);
      await at(38.0, "The decision is recorded: Decided");
    });

    await scene(6, parent, async ({ at }) => {
      await at(0.3, "The parent reloads the payment page (F5): the bank has answered");
      await parent.reload();
      await parent.page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.innerText.trim() === "Approve with MFA" && !b.disabled), { timeout: 20000 });
      await at(2.4, "The approval summary: the facts the parent is about to approve");
      await parent.spot({ sel: '[aria-labelledby="summary-title"]' }, 2800, { wait: false });
      await parent.point({ text: "You pay", sel: "dt", exact: true }, { ms: 900, dx: 60 });
      await at(5.2, "Click 'Approve with MFA'");
      await parent.click({ text: "Approve with MFA", sel: "button", exact: true }, { ms: 1000 });
      await parent.waitText("Approve this payment", 10000);
      await at(8.6, "A fresh MFA code, bound to this payment (246810 in the sandbox)");
      await enterCode(parent);
      await at(13.0, "The status tracker: each step appears as the payment moves");
      await parent.scrollTo({ text: "Status tracker", sel: "h2, h3, div, span", exact: true }, "start");
      await parent.waitText("SETTLED", 45000);
      await at(22.4, "SETTLED: the simulated provider confirmed by a signed webhook");
      await parent.spot({ sel: 'ol[aria-label="Payment timeline"] > li:last-child', dom: true }, 2000);
      await at(25.2, "The page says SETTLED (simulated)");
      await parent.scrollBy(-4000, 1200);
      await parent.spot({ text: "The simulated provider credited the beneficiary", sel: "p, div", up: 1 }, 2600);
    });
    if ((Date.now() - stagedAt) / 1000 > 270) throw new Error("Take 2 took too long: the staged quote may have expired. Stage again and re-record.");

    await scene(7, student, async ({ at }) => {
      await at(0.3, "The student reloads her dashboard (F5)");
      await student.reload();
      await at(3.8, "'As the student you can look and prepare, but only the paying parent can approve'");
      await student.spot({ text: "Household of Demo Parent", sel: "div, p, span, h2, h3", up: 1 }, 3800);
      await at(8.0, "Payments: the same payment");
      await student.click(sidebar("Payments"), { ms: 1000 });
      await student.rect({ text: "8,000.00", sel: "tr" });
      await student.click({ text: "8,000.00", sel: "tr" }, { ms: 900, dx: 150 });
      await student.click({ text: "Open the full page", sel: "a, button" }, { ms: 800 });
      await student.waitText("Status tracker", 20000);
      await at(13.2, "She can follow its status, but there is no approve button for her");
      await student.scrollTo({ text: "Actions", sel: "h2, h3, div", exact: true }, "start");
      await student.spot({ sel: '[aria-labelledby="actions-title"]' }, 3600);
      await at(19.1, "Documents: the checklist the bank may ask for, 0 of 9 ready");
      await student.click(sidebar("Documents"), { ms: 1000 });
      await student.waitText("0 of 9 ready", 15000);
      await student.spot({ text: "0 of 9 ready", sel: "span, div, p" }, 2600);
      await at(24.4, "Student guide");
      await student.click(sidebar("Student guide"), { ms: 1000 });
      await student.rect({ sel: "#g-budget" });
      await at(28.9, "She types a monthly budget: 130000");
      await student.click({ sel: "#g-budget" }, { ms: 900, dx: 40 });
      await student.page.keyboard.down("Control");
      await student.page.keyboard.press("a");
      await student.page.keyboard.up("Control");
      await student.type("130000", 140);
      await sleep(800);
      await at(32.4, "The cities that fit, with rent and total cost");
      await student.scrollTo({ text: "cities fit BDT", sel: "p, div, span" }, "start");
      await student.glide(560, 360, 900);
      await at(34.2, "Details on one city");
      await student.click({ text: "Details", sel: "button", exact: true }, { ms: 900 });
      await sleep(1800);
      await student.page.keyboard.press("Escape");
      await at(38.0, "The Arrival checklist tab");
      await student.click({ text: "Arrival checklist", sel: 'button, [role="tab"]', exact: true }, { ms: 900 });
      await sleep(700);
      await student.scrollBy(520, 3000);
    });

    await scene(8, reviewer, async ({ at }) => {
      await at(0.8, "Click Audit log");
      await reviewer.click(sidebar("Audit log"), { ms: 1100 });
      await reviewer.rect({ text: "Verify the hash chain", sel: "button", exact: true });
      await at(3.4, "Every event holds the hash of the one before");
      await reviewer.scrollBy(300, 3600);
      await at(8.0);
      await reviewer.scrollBy(-300, 2000);
      await at(11.3, "'Verify the hash chain'");
      await reviewer.click({ text: "Verify the hash chain", sel: "button", exact: true }, { ms: 1000 });
      await reviewer.waitText("Chain verified: PASS", 20000);
      await at(13.2, "Chain verified: PASS");
      await reviewer.spot({ text: "Chain verified: PASS", sel: "div, p, span, h2, h3", up: 1 }, 3000);
      await at(16.6, "The newest rows: the clearance and the approval");
      await reviewer.scrollBy(380, 2800);
      await reviewer.glide(640, 330, 1000);
    });

    await scene(9, reviewer, async ({ at }) => {
      await at(0.6, "Back to the verified chain");
      await reviewer.scrollBy(-380, 2200);
      await at(8.1, "The chain verified: what is real is the design");
      await reviewer.spot({ text: "Chain verified: PASS", sel: "div, p, span, h2, h3", up: 1 }, 3600);
    });

    manifest.problems.push(...everyone.flatMap((c) => c.problems));
  } finally {
    fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 1));
    await browser.close();
  }
  if (manifest.problems.length) {
    console.log("browser problems:", manifest.problems);
    process.exitCode = 1;
  } else {
    console.log(`done: ${manifest.scenes.length} scenes, no browser errors${DRY ? " (dry run)" : ""}`);
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
