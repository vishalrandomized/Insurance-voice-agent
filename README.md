# AssureLine

AssureLine is a document-grounded insurance sales advisor with two
separate interfaces:

- `/customer` is a continuous voice conversation for insurance customers.
- `/sales` is an insurer workspace for reviewing leads and callback requests.

The customer hears a short introduction to the uploaded insurance policy, asks
questions grounded in the PDF, inspects citations, and can choose a callback at
the end of the conversation. After confirmation, the callback status is
persisted and appears in the salesperson dashboard.

## Architecture

```text
Next.js on Vercel
  /customer       Customer voice experience
  /sales          Salesperson lead dashboard
        |
        | HTTPS + WebSocket
        v
FastAPI on Railway
  voice orchestration, RAG, callback and lead APIs
        |
        v
Supabase
  Postgres, pgvector, document storage, realtime changes
```

The voice pipeline is built directly:

```text
browser PCM -> streaming STT -> retrieval-grounded LLM -> streaming TTS
```

No LiveKit, Pipecat, or other voice-agent framework is used. Provider adapters
keep STT, LLM, embeddings, and TTS replaceable through environment variables.

## Local Setup

Prerequisites:

- Node.js 20+
- Python 3.11+
- Provider keys for the live stack:
  - `ASSEMBLYAI_API_KEY`
  - `DEEPGRAM_API_KEY`
  - `GEMINI_API_KEY`
- Optional Supabase project for persistent production data

```bash
cp .env.example .env
npm install

python3 -m venv apps/api/.venv
source apps/api/.venv/bin/activate
pip install -r apps/api/requirements.txt
```

Start the API:

```bash
cd apps/api
uvicorn app.main:app --reload --port 8000
```

Start the web application in another terminal:

```bash
npm run dev:web
```

Open:

- Customer: `http://localhost:3000/customer`
- Sales: `http://localhost:3000/sales`
- API health: `http://localhost:8000/health`

When Supabase or provider credentials are absent, development fallbacks allow
the UI and callback flow to be demonstrated without external infrastructure.

For the live stack used by this project, set:

```env
LLM_PROVIDER=gemini
STT_PROVIDER=assemblyai
TTS_PROVIDER=deepgram
EMBEDDING_PROVIDER=gemini
```

## Deployment

### Supabase

1. Create a project and enable the `vector` extension.
2. Apply `supabase/migrations/001_initial.sql`.
3. Create a private bucket for uploaded policy documents.
4. Insert one row in `products` and copy its UUID into `DEFAULT_PRODUCT_ID`.
5. Copy the project URL, anon key, database URL, and service-role key.

### Railway

Deploy `apps/api` as the Railway root and set the API environment values from
`.env.example`.
Set `FRONTEND_ORIGIN` to the final Vercel origin. Railway runs the command in
`apps/api/Procfile`.

### Vercel

Import the repository, set the root directory to `apps/web`, and configure:

```env
NEXT_PUBLIC_API_URL=https://your-api.up.railway.app
NEXT_PUBLIC_WS_URL=wss://your-api.up.railway.app
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

The backend automatically uses Supabase pgvector for document chunks when the
Supabase service-role variables are present; otherwise it uses the in-memory
development store.

Redeploy the API after the Vercel URL is known so CORS and WebSocket origin
validation use the exact production origin.

## Demo Flow

1. Upload the insurance PDF from `/sales`.
2. Open `/customer` and begin a conversation.
3. Listen to the opening policy introduction grounded in the uploaded document.
4. Ask a question answered by the insurance PDF and inspect the citation.
5. Speak while the agent is responding to demonstrate barge-in.
6. End the conversation and confirm the callback proposal.
7. Open `/sales`; the lead appears with callback status `requested`.
8. Mark it `in_progress`, then `completed`.
9. Refresh to verify persistence and inspect the audit timeline.

## Grounding and Safety

- Product claims must be supported by retrieved policy passages.
- Unsupported questions return an explicit abstention.
- The agent does not invent premiums, approval outcomes, claim guarantees, or
  competitor comparisons.
- Customer confirmation is required before a callback request is recorded.
- AI voice disclosure remains visible throughout the customer session.
- API and database credentials stay on the backend.

## Approach and Challenges

The application treats retrieval as a prerequisite to generation. PDFs are
processed page by page, chunked with page metadata, embedded, and searched
before the LLM answers. This provides readable page-level citations instead of
opaque vector-store chunk references.

The main engineering challenge is coordinating independent asynchronous
streams. Every generated response receives a monotonically increasing
generation ID. Barge-in increments that ID, aborts LLM and TTS work, clears
scheduled audio, and causes late events from the old generation to be dropped.
Microphone capture requests browser echo cancellation and gates upstream audio
during playback to reduce feedback loops.

The callback request demonstrates tool use without relying on email or a CRM.
The advisor offers the callback as a closing step, the customer confirms it,
and the backend updates the lead and writes an audit event. The customer sees
confirmation, while the insurer sees the operational toggle in a separate
role-specific UI.

## Verification

```bash
npm run build:web
npm run test:web
npm run test:api
```
