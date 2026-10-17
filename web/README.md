# StudyRoute web (Next.js)

The StudyRoute user interface: Next.js (App Router) and TypeScript, shown by the sandbox for the
FinTechathon 2026 International Track, Topic C. Everything here is a **sandbox with synthetic data**.
No real money moves, and every screen shows the sandbox banner.

It talks to the real StudyRoute API (FastAPI, `backend/`). The browser never works out a number: money,
fees, rates, send dates, runway and the stress test all come from the API's engine, and the UI only
formats and lays them out. Money is always integer minor units plus a currency code.

## Stack

Next.js 16 (static export), React 19, TypeScript (strict), Tailwind CSS 4, shadcn/ui (new-york, zinc)
on Radix, lucide-react, next-themes, sonner, react-hook-form with zod, TanStack Query, date-fns with
`@date-fns/tz` (the Dhaka clock), the shadcn chart (recharts), Geist fonts. Tests: Vitest with Testing
Library, axe-core, and Playwright.

## Run it

Needs Node 22 and the API on port 8000 (`cd backend && uvicorn app.main:create_app --factory`).

```bash
cd web
npm ci                 # also runs the CSP-safe patches in scripts/postinstall.mjs
npm run dev            # http://localhost:3000, proxies /api to the API
```

| Script                 | What it does                                                                      |
| ---------------------- | --------------------------------------------------------------------------------- |
| `npm run dev`          | Dev server on port 3000; `/api` and `/health` go to `STUDYROUTE_API`              |
| `npm run build`        | Static export into `out/`, then writes `security_headers.conf` (CSP hashes)       |
| `npm run typecheck`    | `tsc --noEmit` (strict, `noUncheckedIndexedAccess`)                               |
| `npm run lint`         | ESLint (Next core-web-vitals and TypeScript rules)                                |
| `npm run format:check` | Prettier check (`npm run format` fixes)                                           |
| `npm test`             | Vitest: unit, component and axe accessibility tests                               |
| `npm run e2e`          | Playwright smoke test against `out/` with the real security headers (build first) |

Demo accounts and the sandbox MFA code are shown on the sign-in page when the API runs in sandbox
mode (`SHOW_DEMO_HINTS`).

### Pointing it at another API

The UI calls the same origin under `/api/v1`. That is all the code assumes (`lib/api/client.ts`).

- **Development:** set `STUDYROUTE_API=https://your-api.example` before `npm run dev`; the rewrites in
  `next.config.ts` forward `/api/*` and `/health`.
- **Production:** the build is static files. `nginx.conf` serves them and proxies `/api/` to
  `backend:8000`; change `proxy_pass` there (or put any reverse proxy in front) to use another API.

There is no mock API in the app. The Playwright test answers the API itself (`e2e/mock-api.ts`) so it
needs no backend.

## Strict Content-Security-Policy

The policy has no `unsafe-inline` for scripts or styles: `script-src 'self'` plus the SHA-256 hash of
each inline script that Next exports, and `style-src 'self'`. To make that possible:

- `scripts/csp-hashes.mjs` runs after `next build`, hashes every inline script in `out/` and writes
  `security_headers.conf` from `security_headers.base.conf`. nginx includes that file. It is generated,
  so it is not committed.
- Components render on the client only (`components/providers/client-only.tsx`), so server rendering
  never produces inline `style` attributes.
- `scripts/postinstall.mjs` patches three third-party packages so they stop injecting `<style>`
  elements (sonner, react-style-singleton used by Radix, Radix Select); the CSS they need lives in
  `app/globals.css`. The patches are checked, and the install fails loudly if a package changed.
- Chart colours are set as CSS variables through the style API, not as inline attributes.

If you change the build, restart anything that caches `security_headers.conf` (the lab server in
`scripts/security/prod_like_server.mjs` reads it once at start).

## Motion and interaction

The interface moves, and every piece of it is a stylesheet rule, so the strict policy above is untouched.

| What                                         | Where                             | How                                                                                                                                                    |
| -------------------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Entrances (cards rise, rows fade, chips pop) | `Card`, `Chip`, table bodies      | `animate-rise`, `animate-fade`, `animate-pop` (tokens in `app/globals.css`)                                                                            |
| One after another                            | any list with the `stagger` class | `:nth-child` delays in the stylesheet, never an inline delay                                                                                           |
| Screen change                                | `app/(app)/template.tsx`          | a template is rebuilt on each navigation, so the screen eases in                                                                                       |
| Loading                                      | `Skeleton`                        | a light sweep (`skeleton-shimmer`) instead of a pulse                                                                                                  |
| Press and hover                              | `Button`, `Card`, sidebar         | scale on press, shadow and border on hover, icon nudges                                                                                                |
| Theme change                                 | `ThemeMenu`                       | colours cross-fade for 450 ms through `html.theme-fade`                                                                                                |
| Live budget                                  | Student guide                     | a range slider and the typed amount drive each other; the list refetches 300 ms after the last change, fitting cities are tinted and the count flashes |
| Cost bars                                    | Compare                           | a bar per provider, green for the best and red for a shortfall; only the bar length is worked out in the browser, every amount is the engine's string  |
| Copy                                         | `CopyButton`                      | copies a reference, turns into a tick for two seconds, and claims nothing if the browser refuses                                                       |
| Assistant                                    | chat panel                        | messages rise, three dots show while the engine works                                                                                                  |

Rules to keep:

- **No inline styles in anything that is built into the page.** A value that depends on data (a bar width, the
  slider fill) may be set with a `style` prop only in a component that is drawn after the data has loaded. The
  strict-policy checks (`scripts/security/browser_audit.mjs`, `scripts/csp-interact.mjs`) fail on a violation.
- **Reduced motion is respected.** The global rule in `app/globals.css` cuts every duration and delay to nothing;
  a browser test (`with reduced motion`) checks it. Do not add an animation that carries meaning only in motion.
- **Animations never change a number.** Nothing counts up through invented amounts; a changed figure is shown with
  a flash, not by animating its digits.

## Folder map

```
app/                 routes (App Router): login, and everything behind sign-in in (app)/
components/ui/       shadcn components (edited only where noted in git history)
components/layout/   sidebar, top bar, command menu, assistant sheet, sandbox banner
components/app/      small shared parts: status chips, notices, fields, empty states
components/<screen>/ dashboard, compare, payment, recipients, documents, audit, rules, bank, escrow, sandbox, assistant
lib/api/             fetch client (token refresh, Idempotency-Key, RFC 7807 errors), types, useApi
lib/schemas/         zod schemas (money is checked as text and sent as integer minor units)
lib/domain/          layout-only helpers (the deadline planner's calendar strip)
e2e/                 Playwright smoke test and its API stand-in
scripts/             postinstall patches, CSP hashes, and the browser checks used for the audit
tests/               Vitest setup, fixtures, accessibility tests
```

## Tests

`npm test` runs about 440 tests. They cover the API client (refresh, idempotency, errors), the money and
date helpers, every screen's main behaviour (including the safety rules: a student cannot approve,
a script tag in a name is shown as text, a payment needs MFA, a tampered compliance report is flagged),
and axe-core accessibility checks of each screen. Colour contrast is checked in a real browser by
`scripts/tour.mjs` and the browser audit, because jsdom cannot compute colours.

The browser scripts need Chrome and the API; see `scripts/security/README.md` at the repository root.

## Known differences from the design

- The sidebar is as tall as the window, so a full-page screenshot shows it ending where the first screen
  ends. In the browser it stays in place while the page scrolls.
- The Next.js dev server adds its own round "N" indicator in the corner. It is not in the production build.
- A client-side navigation in the exported app shows `/compare` where a page load shows `/compare/`;
  the server answers both.
