# Running StudyRoute with Docker

One command starts the whole sandbox: the API, the web server and the synthetic demo data.

```bash
docker compose up --build
```

Open **http://localhost:8080** and sign in with a demo account (see the README). Stop with
`Ctrl+C`; start again with `docker compose up` (no rebuild needed unless the code changed).

## What you need

- Docker with Compose v2 (`docker compose version` should print a version).
- **Windows:** Docker Desktop with the WSL 2 backend. Install it, restart when it asks, start Docker
  Desktop and wait until it says "Engine running". Installing needs administrator rights.
- **macOS / Linux:** Docker Desktop or Docker Engine with the Compose plugin.
- About 1.5 GB of disk for the images and port **8080** free on your machine.

Nothing else is required: no `.env`, no API key, no database server. The app starts in sandbox mode
with generated throw-away secrets.

## What starts

| Container | Image | Role | Port |
|-----------|-------|------|------|
| `web` | nginx (unprivileged) with the built React UI | Serves the UI, proxies `/api/` and `/health` to the API, sends the security headers | **8080**, the only published port |
| `backend` | Python 3.12 slim, non-root user | FastAPI sandbox API; seeds demo data on first start | 8000, reachable only from `web` |

`web` waits until the API reports healthy. Both containers have health checks, and the data
(SQLite database, generated sandbox secrets) lives in the named volume `studyroute-data`, so your
demo state survives a restart.

## Everyday commands

```bash
docker compose up --build            # build and start (add -d to run in the background)
docker compose ps                    # state and health of both containers
docker compose logs -f backend       # follow the API log (tokens, e-mails and account numbers are redacted)
docker compose down                  # stop, keep the data
docker compose down -v               # stop and DELETE the data: the next start re-seeds
```

Run the repository's own scripts inside the API container:

```bash
docker compose exec backend python -m app.scripts.demo_flow      # 14-step demo check
docker compose exec backend python -m app.scripts.tamper_audit   # edit the log, then Verify FAIL
docker compose exec backend python -m app.scripts.check_ai       # after you add an LLM key
```

The sign-in endpoints allow 10 requests a minute per address, so wait a minute between two runs of
`demo_flow`.

## Check that the stack is healthy

With the stack running, from the repository root on the host:

```bash
python scripts/docker_smoke.py                       # defaults to http://localhost:8080
```

It uses only the Python standard library and prints OK or FAIL for each check: the app shell is
served, the browser security headers are present exactly once, the API answers through the proxy
with the sandbox marker, errors are RFC 7807, an oversized body is refused. The exit code is 0 when
everything passes, 1 when a check fails and 2 when nothing is listening. The CI `docker` job runs
the same script against a freshly built stack.

## Settings

Copy `.env.example` to `.env` next to `docker-compose.yml` to change anything; every value is
optional and an empty value keeps the default. The ones people ask about:

| Variable | Effect |
|----------|--------|
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` | Turn on model mode for the assistant. Empty means template mode, which needs no key |
| `SHOW_DEMO_HINTS=false` | Hide the demo-account buttons and MFA hint on the sign-in page |
| `SEED_DEMO_PASSWORD`, `SANDBOX_MFA_CODE` | Replace the documented demo password and MFA code |
| `APP_ENV=production` | Refuses to start without real secrets; skips seeding. Not for the competition demo |

After changing `.env`, run `docker compose up --build` again so the containers pick it up.

## Optional: a stricter container set-up

```bash
docker compose -f docker-compose.yml -f docker-compose.hardened.yml up --build
```

Adds a read-only root filesystem, dropped Linux capabilities and `no-new-privileges` to both
containers. It was run for real (see "What was and was not tested"): both containers start
healthy, the root filesystem is read-only, and the smoke script and the demo pass. If it ever fails
to start on your machine, fall back to the normal command.

## Troubleshooting

| Symptom | Likely cause and fix |
|---------|----------------------|
| `docker: command not found` or "cannot connect to the Docker daemon" | Docker is not installed or not running. On Windows start Docker Desktop and wait for "Engine running" |
| "port is already allocated" for 8080 | Something else uses 8080. Stop it, or change `"8080:8080"` in `docker-compose.yml` to e.g. `"8081:8080"` and open that port |
| `web` stays in "Created" or "waiting" | The API is not healthy yet or crashed. `docker compose logs backend` shows why |
| The page loads but sign-in fails with a network error | You opened a URL other than the one `web` serves (for example port 8000). Use http://localhost:8080 |
| Sign-in says too many attempts | The limit is 10 a minute per address. Wait a minute |
| The Bank network screen says it is not set up | The database predates the bank simulation. `docker compose restart backend` adds it on start (the entrypoint checks every time), or run `docker compose exec backend python -m app.scripts.seed` |
| Old data or a changed password does not appear | The volume still holds the first run. `docker compose down -v`, then `up --build` |
| `sh: ... not found` or `\r` errors in the entrypoint | A file was saved with Windows line endings. The repository's `.gitattributes` forces LF on checkout, and `scripts/make_submission.py` writes LF into the zip. Re-clone or convert the file to LF |
| Build fails while installing Python or npm packages | No internet or a proxy. Retry; both lock files are pinned, so the same versions are fetched each time |

## What was and was not tested

### Run for real, on 15 October 2026

The stack was built and run with **real Docker** from a clean copy: the submission archive
(`dist/studyroute-submission.zip`, commit `3eb6a57`) unzipped in a fresh directory.

- **Where:** Docker Engine 29.1.3 and Docker Compose 2.40.3 (Ubuntu 24.04 packages, `amd64`) inside
  an Ubuntu 24.04 virtual machine run by portable QEMU 11.1 on the Windows 11 development machine,
  because Docker Desktop could not be installed there (no administrator rights). The VM listened
  only on `127.0.0.1`; the scripts below ran from the Windows host through the forwarded port 8080.
- **`docker compose up --build`:** both images built (the backend's `pip install` from the lock
  file and the frontend's `npm ci` and `vite build` included). The backend became healthy, then
  `web` started. Images: backend 366 MB (Python 3.12 slim), web 75 MB (nginx 1.27.5 unprivileged).
- **`python scripts/docker_smoke.py`:** all checks passed.
- **`docker compose exec backend python -m app.scripts.demo_flow`:** all 14 steps passed (53 OK
  lines), including the smart escrow and the audit anchor.
- **`scripts/security/browser_audit.mjs`** (real Chrome, production content security policy):
  40 of 40 checks passed through the container's own nginx.
- **Containers:** the backend runs as user 10001 and the web server as the unprivileged `nginx`
  user. Only port 8080 is published; the API's port 8000 is reachable only from `web`. Nothing in
  the backend log held a token, a private key or an IBAN; the only matches were the seed banner
  that prints the documented demo accounts, password and MFA code.
- **Data survives:** after `docker compose down` and `up`, the audit chain still verified
  (81 events, then 82 after the next sign-in), and the escrow chain replayed from the database with
  its 12 transactions and its audit anchor intact.
- **The hardened overlay** (`docker-compose.hardened.yml`) started from an empty volume with both
  containers healthy. Docker confirmed `ReadonlyRootfs=true`, all capabilities dropped and
  `no-new-privileges`; a write outside the data volume was refused ("Read-only file system"). The
  smoke script and the full 14-step demo passed on it. The only message is nginx's harmless
  "can not modify default.conf (read-only file system?)" from its IPv6 start-up script.

**Not covered by that run:** Docker Desktop on Windows or macOS (the VM was Linux `amd64`), `arm64`
images, a different base-image digest tomorrow (the tags `python:3.12-slim`, `node:22-alpine` and
`nginxinc/nginx-unprivileged:1.27-alpine` move), and the GitHub Actions `docker` job, which runs
when the repository is pushed.

### Checked piece by piece before that

- **The pinned dependencies fit the image.** `backend/requirements.txt` was resolved for the
  container's platform (Linux, Python 3.12, `x86_64` and `aarch64`): all 59 pins have a published
  wheel. The frontend lock file carries the Linux (including musl) native builds.
- **The API as the image runs it** (clean environment from the lock file, the real
  `docker-entrypoint.sh`) and **the repository's `nginx.conf` in a real nginx 1.27**, natively on
  Windows. Those runs found and fixed two real defects: the proxy added the web page's security
  headers on top of the API's own (each API response carried them twice), and the demo tripped the
  10-a-minute sign-in limit the first time it ran against the real rate limits (it now waits as the
  server asks; a test keeps it so).
- Static tests in `backend/tests/test_docker_config.py` and `test_docker_smoke.py`.
- The GitHub Actions `docker` job builds both images, starts the stack with `docker compose up`,
  runs `scripts/docker_smoke.py` and the demo flow, and tears it down.

### Reproduce it

On any machine with Docker, from a clean clone or the unzipped archive:

```bash
docker compose up --build
python scripts/docker_smoke.py
docker compose exec backend python -m app.scripts.demo_flow
docker compose down -v
```
