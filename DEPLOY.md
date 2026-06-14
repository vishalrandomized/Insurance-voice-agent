# Deployment runbook — AssureLine (all on Railway + Supabase)

Monorepo: `apps/api` (FastAPI + voice WebSocket) and `apps/web` (Next.js 15). Two
Railway services from one GitHub repo, plus Supabase for leads/callbacks.
Embeddings stay in-memory (`RAG_VECTOR_STORE=memory`) for speed; the policy PDF
is auto-seeded on startup (Railway's filesystem is ephemeral).

Config-as-code is committed, so most build settings are automatic:
- `apps/api/railway.json` → API service (Dockerfile build, watch `apps/api/**`, `/health`).
- `railway.json` (repo root) → web service (Dockerfile `apps/web/Dockerfile`, watch `apps/web/**` + contracts + root manifests).

---

## 0. Prerequisites (done)
- GitHub repo pushed: `vishalrandomized/Insurance-voice-agent` (branch `main`).
- Supabase project created, migration `supabase/migrations/001_initial.sql` run, and the product row inserted:
  `insert into products (id,name) values ('11111111-1111-4111-8111-111111111111','Setu Sampoorna Health Plan');`

## 1. API service (Railway)
1. New Project → Deploy from GitHub repo → pick the repo.
2. Service → **Settings → Root Directory = `apps/api`** (required — this is where the Dockerfile + railway.json live; also makes the repo-root railway.json apply to the *web* service only).
3. **Settings → Region** = Singapore (closest to India + Sarvam).
4. **Variables** (Raw Editor) — use the real keys (kept out of this repo):
   ```
   FRONTEND_ORIGIN=https://<WEB-DOMAIN>.up.railway.app   # set after web deploy (step 3)
   LLM_PROVIDER=openai
   OPENAI_API_KEY=<sarvam key>
   OPENAI_BASE_URL=https://api.sarvam.ai/v1
   LLM_MODEL=sarvam-105b
   LLM_MAX_TOKENS=4000
   LLM_REASONING_EFFORT=low
   LLM_TEMPERATURE=0.2
   EMBEDDING_PROVIDER=gemini
   EMBEDDING_MODEL=gemini-embedding-2
   GEMINI_API_KEY=<gemini key>
   STT_PROVIDER=assemblyai
   STT_MODEL=u3-rt-pro
   ASSEMBLYAI_API_KEY=<key>
   TTS_PROVIDER=deepgram
   TTS_MODEL=aura-2-thalia-en
   DEEPGRAM_API_KEY=<key>
   SUPABASE_URL=https://<ref>.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=<sb_secret_…>
   DEFAULT_PRODUCT_ID=11111111-1111-4111-8111-111111111111
   RAG_VECTOR_STORE=memory
   ```
5. **Deploy** (build is the Dockerfile via railway.json). **Settings → Networking → Generate Domain** → this is the **API URL**. Verify `https://<api>/health` → `{"status":"ok"}`.

> If a fix on `main` doesn't auto-deploy, the dashboard watch path is stale — trigger one manual **Redeploy**; `railway.json`'s `watchPatterns` then becomes authoritative.

## 2. Web service (Railway, same project)
1. **New → GitHub Repo** → same repo (second service).
2. **Settings → Root Directory** = leave **blank (repo root)** — the repo-root `railway.json` builds `apps/web/Dockerfile` with the workspace as context. Do NOT set `apps/web`.
3. **Variables** (point at the API domain from step 1):
   ```
   NEXT_PUBLIC_API_URL=https://<API-DOMAIN>.up.railway.app
   NEXT_PUBLIC_WS_URL=wss://<API-DOMAIN>.up.railway.app
   ```
   These are baked in at **build time** (Railway passes them to the Dockerfile as build args). If you change them later you must **redeploy** the web service, not just restart.
4. **Deploy** → **Generate Domain** → this is the public **web URL**.

## 3. Wire-up
On the **API service**, set `FRONTEND_ORIGIN=https://<WEB-DOMAIN>.up.railway.app` → it redeploys. (CORS + WebSocket origin allow-list use this single origin.)

## 4. Verify
- `GET https://<api>/health` → ok; API logs show `[startup] document pre-warm complete`.
- Open `https://<web>/customer` (HTTPS → mic allowed) → Start → hear Riya → ask a question → grounded, cited answer in Indian number speech.
- End call → spoken callback offer → "yes" → row appears in Supabase `leads` with `callback_status='requested'`; `https://<web>/sales` shows it.

## Gotchas
- **Watch paths**: API watches `apps/api/**`, web watches `apps/web/**` + `packages/contracts/**` + root manifests. A change outside a service's patterns won't redeploy it (by design).
- **NEXT_PUBLIC_* is build-time** for the client bundle — redeploy web after changing the API URL.
- **Ephemeral FS**: uploads don't survive restarts; the bundled `apps/api/seed/policy.pdf` is auto-ingested at startup, so the agent is always grounded. Leads/callbacks persist in Supabase.
- **Latency**: ~6–8 s/answer is Sarvam reasoning, unaffected by hosting. Supabase is off the voice path.
