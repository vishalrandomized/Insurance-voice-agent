# Architecture — AssureLine voice orchestration

AssureLine runs a realtime **STT → LLM (RAG) → TTS** phone-style loop **without
LiveKit, Pipecat, or any WebRTC stack**. The transport is a plain WebSocket
carrying base64 PCM; the pipeline is a hand-rolled `VoiceOrchestrator` class
coordinated with `asyncio`; the browser captures and plays audio with the Web
Audio API. This doc explains where that orchestration lives and the trade-offs of
building it framework-free.

> Deployment/runbook lives in `DEPLOY.md`. This file is about how the realtime
> loop is wired.

---

## What LiveKit / Pipecat do — and what we use instead

| Role | LiveKit / Pipecat would give you | What this app uses |
|---|---|---|
| **Transport** (move audio in realtime) | LiveKit: WebRTC — SFU, Opus codec, jitter buffer, NAT traversal, echo cancellation | A plain **WebSocket** (`/ws/voice/{id}`) carrying **JSON**; audio is **base64 linear16 PCM, 24 kHz mono** |
| **Pipeline** (VAD → STT → LLM → TTS, turn-taking, interruption) | Pipecat: a framework that wires the stages and routes "frames" | A custom **`VoiceOrchestrator`** orchestrating provider objects with `asyncio` tasks/queues |
| **VAD / turn-taking** | Pipecat's built-in VAD + interruption handling | Browser-side **RMS VAD** (half-duplex) + a server-side **`generation_id`** scheme |
| **Client** | LiveKit client SDK | Browser **Web Audio** (AudioWorklet capture + scheduled buffer playback) over the raw WebSocket |

---

## End-to-end flow

```
┌─────────────────────────── Browser (apps/web/lib/audio) ───────────────────────────┐
│  mic → AudioWorklet → downsample 24kHz → ~100ms batch → PCM16 → base64               │
│        │ (half-duplex: muted while agent speaks, via agentBusyRef)                   │
└────────┼────────────────────────────────────────────────────────────────────────────┘
         │  WS: { type:"audio.append", audio:"<base64 pcm>" }
         ▼
┌─────────────────────────── FastAPI (apps/api/app) ──────────────────────────────────┐
│  websocket/router.py  ──>  VoiceOrchestrator (voice/orchestrator.py)                 │
│                                 │                                                     │
│        AssemblyAI STT (WS) <────┤ forwards PCM ; receives partial/final transcripts  │
│                                 │                                                     │
│        on FINAL transcript ─────▶ response_stream  (RAG over PDF + Sarvam LLM)        │
│                                 │      yields text deltas                             │
│                                 ▼                                                     │
│                          SentenceBuffer (voice/segmenter.py)  → speakable segments    │
│                                 │  normalize_for_speech (voice/speech_text.py)        │
│                                 ▼                                                     │
│                          Deepgram TTS (WS) → PCM bytes → base64                       │
└─────────────────────────────────┼────────────────────────────────────────────────────┘
         │  WS: { type:"agent.audio.chunk", audio:"<base64 pcm>" }
         ▼
   Browser playback.ts → decode PCM16 → Web Audio scheduled buffer sources (60ms lead)
```

---

## The three layers

### 1. Transport endpoint — `apps/api/app/websocket/router.py`
- `@router.websocket("/ws/voice/{session_id}")` accepts the socket, then runs a
  receive loop that JSON-parses each client event, validates it
  (`_validate_client_event`), and dispatches to the orchestrator.
- A **duplicate-session guard** (`app/websocket/manager.py`,
  `VoiceSessionRegistry.acquire/release`) allows only one live socket per
  `session_id` (a second connection is closed with WS 1008).
- Providers and the orchestrator are created **per session** from
  `VoiceConfig.from_env()`.

This is the role LiveKit's media server would play — except it's TCP/WebSocket +
JSON, not a WebRTC media track.

### 2. The orchestrator — `apps/api/app/voice/orchestrator.py`
`VoiceOrchestrator` is "the orchestration." Per session it holds an STT provider,
a TTS provider, and the `response_stream` callable (the RAG/LLM generator defined
in `router.py`). Key methods:

- `start()` — spawns a background task to open the STT stream and emits
  `session.ready` immediately (so the greeting can start while STT handshakes).
- `append_audio()` / `commit_audio()` — forward client PCM to the STT provider;
  `append_audio` deliberately does **not** open a turn (silence frames mustn't
  kill an in-progress answer).
- `submit_text()` — text path (used for the hardcoded greeting trigger and typed
  input); opens a turn and runs a response directly, bypassing STT.
- `_consume_stt()` — background loop over STT events: a **partial** transcript
  opens a turn; a **final** transcript fires `_run_response`.
- `_run_response()` — iterates the LLM stream, emits `agent.text.delta`, pushes
  text into the `SentenceBuffer`, and enqueues completed segments for TTS.
- `_stream_tts_segments()` — pulls segments, runs `normalize_for_speech`, calls
  the TTS provider, and emits each PCM chunk as base64 `agent.audio.chunk`.
- `cancel_response()` / `close()` — interruption and teardown.
- `_emit()` — single choke point for outbound events; serialized with a lock and
  **drops stale-generation events** (unless `allow_stale=True`).

**Turn-taking / interruption** is a monotonic **`generation_id`** plus
`_is_current(generation)` checks sprinkled through `_run_response` and
`_stream_tts_segments`. Opening a new turn bumps the id; any task or event from an
older generation is cancelled or dropped. This is the home-grown equivalent of
Pipecat's frame/interruption management.

Supporting modules:
- `app/voice/segmenter.py` — `SentenceBuffer.push()/flush()` splits the streaming
  LLM text into TTS-sized chunks at sentence boundaries (falling back to soft
  comma/space breaks past ~180 chars), so speech starts before the full answer is
  generated.
- `app/voice/speech_text.py` — `normalize_for_speech()` strips `[C1]` citation
  markers and converts "₹1 Crore"/percentages/acronyms to spoken forms for the
  audio only (the on-screen transcript keeps the original text).

### 3. Browser — `apps/web/lib/audio/`
- `microphone.ts` — `getUserMedia` (with browser echo cancellation / noise
  suppression) → an inline **AudioWorklet** captures raw PCM → downsample to
  24 kHz → batch ~100 ms → `pcm.ts` encodes Float32→PCM16→base64 → send
  `audio.append`. Also computes per-frame **RMS VAD** for half-duplex turn
  detection.
- `playback.ts` — decodes each base64 chunk (PCM16→Float32) into an AudioBuffer
  and schedules it as a `BufferSource` ~60 ms ahead of the previous one, so
  chunks play gaplessly. Tracks a `generationId` to drop stale audio.
- `use-customer-voice-session.ts` — the WebSocket client and state machine; owns
  the **`agentBusyRef`** half-duplex gate (mic is muted while the agent speaks,
  re-opened ~400 ms after playback drains).
- `pcm.ts` — PCM16 ↔ base64 helpers and `INPUT_SAMPLE_RATE = 24000`.

This replaces the LiveKit client SDK.

---

## WebSocket event protocol

**Client → server** (validated in `_validate_client_event`, `router.py`):

| Event | Payload | Meaning |
|---|---|---|
| `session.start` | `{sessionId}` | begin the session (opens STT) |
| `audio.append` | `{sessionId, audio}` | a base64 PCM mic batch |
| `audio.commit` | `{sessionId}` | end-of-utterance marker (force STT endpoint) |
| `text.submit` | `{sessionId, text}` | typed input / system triggers (greeting, end-call) |
| `response.cancel` | `{sessionId, generationId}` | interrupt the current answer |
| `session.end` | `{sessionId}` | hang up |

**Server → client** (emitted via `_emit` in `orchestrator.py`):

| Event | Meaning |
|---|---|
| `session.ready` | session initialized; includes audio format |
| `transcript.partial` / `transcript.final` | streaming STT results |
| `agent.text.delta` / `agent.text.complete` | streaming LLM text / final text |
| `agent.audio.chunk` | base64 PCM TTS audio |
| `citation.created` | a grounding citation for the current answer |
| `agent.response.cancelled` | the in-flight answer was interrupted |
| `session.error` | recoverable/terminal error |

**Audio format:** base64 **linear16 PCM, 24 kHz, mono** both directions
(`VOICE_SAMPLE_RATE`, default 24000). No Opus, no container.

---

## Providers (swappable via env)

Selected in `app/voice/config.py` (`VoiceConfig.from_env`) and the
`app/providers/*/factory.py` files:

- **STT:** AssemblyAI streaming (`u3-rt-pro`) over `wss://streaming.assemblyai.com/v3/ws`
  (`app/providers/stt/assemblyai.py`). An OpenAI Realtime STT provider also exists.
- **TTS:** Deepgram Aura (`aura-2-thalia-en`, linear16/24 kHz) over
  `wss://api.deepgram.com/v1/speak` (`app/providers/tts/deepgram.py`). An OpenAI
  TTS provider also exists.
- **LLM:** Sarvam (OpenAI-compatible) reached through the RAG `response_stream`
  (`app/websocket/router.py` → `app/rag/service.py`), grounded on the policy PDF.

The orchestrator only depends on the provider **Protocols** (`providers/stt/base.py`,
`providers/tts/base.py`), so any of these can be swapped without touching the
pipeline.

---

## Turn-taking & barge-in

- **Half-duplex** today: while the agent speaks, the browser mutes the mic
  (`agentBusyRef` in `use-customer-voice-session.ts`); the server tracks the
  active turn with `generation_id`.
- A **barge-in detector exists but is intentionally wired off** — see the comment
  near `use-customer-voice-session.ts:361`. Voice-activated interruption was
  destabilizing turn/generation state (lost transcripts, resets), so it was
  reverted to stable turn-by-turn. To re-enable, pass an `onBargeIn: () =>
  interrupt()` callback to `microphone.start(...)`; the `interrupt()` helper and
  the server `response.cancel` path are already in place.

---

## Trade-offs of going framework-free

What we gained: a tiny dependency surface, full control over the loop, and a setup
that's easy to reason about for a 1:1 half-duplex demo.

What we gave up vs. LiveKit/Pipecat:
- **Bandwidth** — raw PCM is ~16× larger than Opus; fine on good networks, wasteful on poor ones.
- **Network resilience** — WebSocket is TCP, so packet loss causes head-of-line blocking; there's no jitter buffer or FEC like WebRTC provides.
- **Echo/AEC** — we rely on the browser's `getUserMedia` echo cancellation plus half-duplex muting, rather than a media server's processing.
- **Interruption** — no framework-grade barge-in; ours is disabled for stability.

When to migrate: if you need robust full-duplex barge-in, multi-party calls, poor-network resilience, or telephony (SIP) ingress, that's the point to adopt LiveKit (transport) and/or Pipecat (pipeline). For the current single-user, grounded-sales demo, the hand-rolled stack is sufficient and lower-overhead.
