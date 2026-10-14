// Serves frontend/dist with the project's REAL security headers (frontend/security_headers.conf) and
// proxies /api and /health to the API, the way nginx does. Used to test the app under the production CSP.
//   cd frontend && npm run build
//   node ../scripts/security/prod_like_server.mjs 8090 8002
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const DIST = path.join(ROOT, "frontend", "dist");
const API = { host: "127.0.0.1", port: Number(process.argv[3] ?? 8002) };
const PORT = Number(process.argv[2] ?? 8090);
const headers = {};
for (const line of fs.readFileSync(path.join(ROOT, "frontend", "security_headers.conf"), "utf8").split("\n")) {
  const m = line.match(/^add_header\s+(\S+)\s+"(.*)"\s+always;/);
  if (m) headers[m[1]] = m[2];
}
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".json": "application/json" };

http.createServer((req, res) => {
  if (req.url.startsWith("/api/") || req.url === "/health") {
    const forwarded = { ...req.headers, host: `${API.host}:${API.port}`, "x-forwarded-for": req.socket.remoteAddress };
    const up = http.request({ ...API, path: req.url, method: req.method, headers: forwarded }, (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
    up.on("error", () => { res.writeHead(502); res.end(); });
    req.pipe(up);
    return;
  }
  const root = path.resolve(DIST);
  let file = path.resolve(root, "." + decodeURIComponent(req.url.split("?")[0]));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(root, "index.html");
  res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] ?? "application/octet-stream", "Cache-Control": file.endsWith("index.html") ? "no-cache" : "public, max-age=31536000, immutable", ...headers });
  fs.createReadStream(file).pipe(res);
}).listen(PORT, "127.0.0.1", () => console.log(`prod-like server on ${PORT}, CSP: ${headers["Content-Security-Policy"]}`));
