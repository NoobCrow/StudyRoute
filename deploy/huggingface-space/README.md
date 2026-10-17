---
title: StudyRoute Cloud Assistant
emoji: 🎓
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 6.30.0
python_version: 3.10
app_file: app.py
pinned: false
license: apache-2.0
models:
  - Qwen/Qwen3-4B-Instruct-2507
---
# StudyRoute ZeroGPU model server

Deployment scaffold, NOT an already-deployed or live-tested service.

Copy ONLY the files in this folder to your own Gradio Space. Select **ZeroGPU**
hardware (not CPU Basic); eligibility, quota and availability are decided by HF.
Model weights download on HF, never on the StudyRoute PC. The 4B model is a
practical multilingual candidate, not a claim of "the best" model or perfect financial accuracy.

1. In Space Settings > Variables and secrets add secret **SPACE_APP_SECRET**:
   a randomly generated string of at least 32 characters. Never commit it.
2. Confirm the Space builds and reaches Running. First download/startup may take time.
3. Copy its direct HTTPS origin (https://owner-space.hf.space) to StudyRoute's
   server-side HF_SPACE_URL. Do not use the huggingface.co/spaces/... browser URL.
4. Add HF_TOKEN (a least-privilege HF token permitted to access this Space), and
   HF_SPACE_APP_SECRET matching the secret above to the local server .env.
5. Restart StudyRoute's backend and test a synthetic question.

Public Space source is visible. Keep this shared access secret exclusively in
Space Secrets and the backend .env. Do not upload customer files, API keys or
StudyRoute .env to this repo. The public UI cannot call generation without the
secret. Public source does not mean confidential data should be sent to it.

The backend speaks the pinned Gradio runtime's /gradio_api/call/respond HTTP+SSE
API with two inputs: request JSON and the shared app secret. HF_TOKEN is sent in
an Authorization header. No other user's public demo is used as a backend.
This installation shares the operator token's quota. It is NOT per app user.

Official references:
- https://huggingface.co/docs/hub/en/spaces-zerogpu
- https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
- https://www.gradio.app/guides/querying-gradio-apps-with-curl

This app does not log prompts. Gradio/HF/provider infrastructure can process
requests under its own policies. Use synthetic data only. Free quotas, queues,
sleep/restarts, inference quality and runtime dependencies require a real
account-level test before using the demo. Do not disable security controls.
