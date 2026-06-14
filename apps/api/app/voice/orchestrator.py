from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.providers.stt import STTEventType, STTProvider
from app.providers.tts import TTSProvider

from .config import VoiceConfig
from .segmenter import SentenceBuffer
from .speech_text import normalize_for_speech


SendEvent = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ResponseContext:
    session_id: str
    generation_id: int


@dataclass(frozen=True, slots=True)
class ResponseDelta:
    text: str = ""
    citations: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    callback_proposal: dict[str, Any] | None = None


class ResponseStream(Protocol):
    def __call__(
        self, transcript: str, context: ResponseContext
    ) -> AsyncIterator[ResponseDelta]: ...


async def demo_response_stream(
    transcript: str, context: ResponseContext
) -> AsyncIterator[ResponseDelta]:
    message = (
        "Demo mode received your question. Connect the grounded response "
        "handler to answer from the uploaded insurance document."
    )
    for token in message.split():
        await asyncio.sleep(0)
        yield ResponseDelta(text=f"{token} ")


class VoiceOrchestrator:
    def __init__(
        self,
        *,
        session_id: str,
        stt: STTProvider,
        tts: TTSProvider,
        response_stream: ResponseStream,
        send_event: SendEvent,
        config: VoiceConfig,
    ) -> None:
        self.session_id = session_id
        self._stt = stt
        self._tts = tts
        self._response_stream = response_stream
        self._send_event = send_event
        self._config = config
        self._generation_id = 0
        self._turn_open = False
        self._closed = False
        self._stt_ready = False
        self._stt_task: asyncio.Task[None] | None = None
        self._response_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()

    @property
    def generation_id(self) -> int:
        return self._generation_id

    async def start(self) -> None:
        # Connect STT in the background and signal readiness immediately, so the
        # hardcoded greeting starts playing without waiting on the STT provider's
        # WebSocket handshake (~1s). The mic is gated (half-duplex) while the
        # agent speaks, so STT finishes connecting before any user audio arrives.
        self._stt_task = asyncio.create_task(
            self._start_stt(), name=f"stt-events-{self.session_id}"
        )
        await self._emit(
            "session.ready",
            vad=self._config.vad.as_client_dict(),
            audio={
                "format": self._tts.content_type,
                "sampleRate": self._tts.sample_rate,
            },
        )

    async def _start_stt(self) -> None:
        await self._stt.start()
        self._stt_ready = True
        await self._consume_stt()

    async def append_audio(self, audio_base64: str) -> None:
        if self._closed:
            return
        self._validate_audio_size(audio_base64)
        if not self._stt_ready:
            # STT is still connecting (greeting is playing); safe to drop these
            # early frames since the mic is gated until the agent finishes.
            return
        # The client streams mic audio continuously (including silence between
        # utterances). Forwarding it to STT must NOT open a new turn or cancel
        # the in-flight response — otherwise silence frames arriving while the
        # agent is still generating its answer kill that answer. A new turn is
        # opened only when STT actually recognizes speech (see _consume_stt).
        await self._stt.send_audio(audio_base64)

    async def commit_audio(self) -> None:
        if self._closed or not self._stt_ready:
            return
        await self._stt.commit()

    async def submit_text(self, text: str) -> None:
        transcript = text.strip()
        if not transcript:
            return
        await self._start_new_turn()
        generation = self._generation_id
        self._turn_open = False
        task = asyncio.create_task(
            self._run_response(transcript, generation),
            name=f"text-response-{self.session_id}-{generation}",
        )
        self._response_task = task
        task.add_done_callback(self._clear_finished_response)

    async def cancel_response(self, requested_generation: int | None = None) -> None:
        if (
            requested_generation is not None
            and requested_generation != self._generation_id
        ):
            return
        cancelled_generation = self._generation_id
        self._generation_id += 1
        self._turn_open = False
        await self._cancel_response_task()
        await self._emit(
            "agent.response.cancelled",
            generation_id=cancelled_generation,
            allow_stale=True,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._cancel_response_task()
        if self._stt_task:
            self._stt_task.cancel()
            await asyncio.gather(self._stt_task, return_exceptions=True)
        await asyncio.gather(
            self._stt.close(), self._tts.close(), return_exceptions=True
        )

    async def _start_new_turn(self) -> None:
        previous_generation = self._generation_id
        had_response = self._response_task is not None
        self._generation_id += 1
        self._turn_open = True
        await self._cancel_response_task()
        if had_response:
            await self._emit(
                "agent.response.cancelled",
                generation_id=previous_generation,
                allow_stale=True,
            )

    async def _consume_stt(self) -> None:
        try:
            async for event in self._stt.events():
                if event.type is STTEventType.PARTIAL:
                    # First recognized speech after a closed turn = the user has
                    # started a new utterance: open a turn (which cancels any
                    # response still playing — i.e. barge-in).
                    if not self._turn_open:
                        await self._start_new_turn()
                    await self._emit(
                        "transcript.partial",
                        generation_id=self._generation_id,
                        text=event.text,
                    )
                elif event.type is STTEventType.FINAL:
                    transcript = event.text.strip()
                    if not transcript:
                        self._turn_open = False
                        continue
                    # Handle a final with no preceding partial (short utterance).
                    if not self._turn_open:
                        await self._start_new_turn()
                    self._turn_open = False
                    generation = self._generation_id
                    await self._emit(
                        "transcript.final",
                        generation_id=generation,
                        text=transcript,
                    )
                    await self._cancel_response_task()
                    task = asyncio.create_task(
                        self._run_response(transcript, generation),
                        name=f"voice-response-{self.session_id}-{generation}",
                    )
                    self._response_task = task
                    task.add_done_callback(self._clear_finished_response)
                else:
                    await self._emit(
                        "session.error",
                        generation_id=self._generation_id,
                        code=event.error_code or "stt_error",
                        message=event.text or "Transcription failed",
                        recoverable=event.recoverable,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._emit(
                "session.error",
                code="stt_event_loop_failed",
                message=str(exc),
                recoverable=True,
            )

    async def _run_response(self, transcript: str, generation: int) -> None:
        segment_queue: asyncio.Queue[str | None] = asyncio.Queue()
        buffer = SentenceBuffer(self._config.max_tts_segment_chars)
        full_text: list[str] = []
        tts_task = asyncio.create_task(
            self._stream_tts_segments(segment_queue, generation),
            name=f"tts-{self.session_id}-{generation}",
        )
        try:
            context = ResponseContext(self.session_id, generation)
            async for delta in self._response_stream(transcript, context):
                if not self._is_current(generation):
                    return
                if delta.text:
                    full_text.append(delta.text)
                    await self._emit(
                        "agent.text.delta",
                        generation_id=generation,
                        delta=delta.text,
                    )
                    for segment in buffer.push(delta.text):
                        await segment_queue.put(segment)
                for citation in delta.citations:
                    await self._emit(
                        "citation.created",
                        generation_id=generation,
                        citation=citation,
                    )
                if delta.callback_proposal:
                    await self._emit(
                        "callback.proposed",
                        generation_id=generation,
                        **delta.callback_proposal,
                    )

            for segment in buffer.flush():
                await segment_queue.put(segment)
            await segment_queue.put(None)
            await tts_task
            if self._is_current(generation):
                await self._emit(
                    "agent.text.complete",
                    generation_id=generation,
                    text="".join(full_text).strip(),
                )
        except asyncio.CancelledError:
            tts_task.cancel()
            await asyncio.gather(tts_task, return_exceptions=True)
            raise
        except Exception as exc:
            tts_task.cancel()
            await asyncio.gather(tts_task, return_exceptions=True)
            if self._is_current(generation):
                await self._emit(
                    "session.error",
                    generation_id=generation,
                    code="response_stream_failed",
                    message=str(exc),
                    recoverable=True,
                )

    async def _stream_tts_segments(
        self, queue: asyncio.Queue[str | None], generation: int
    ) -> None:
        while True:
            segment = await queue.get()
            if segment is None:
                return
            # Normalize numbers/currency/acronyms and drop citation markers for
            # speech only (the on-screen transcript keeps the original text).
            spoken = normalize_for_speech(segment)
            if not spoken:
                continue
            async for audio in self._tts.stream_audio(spoken, generation):
                if not self._is_current(generation):
                    return
                await self._emit(
                    "agent.audio.chunk",
                    generation_id=generation,
                    audio=base64.b64encode(audio).decode("ascii"),
                )

    async def _cancel_response_task(self) -> None:
        task = self._response_task
        self._response_task = None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def _clear_finished_response(self, task: asyncio.Task[None]) -> None:
        if self._response_task is task:
            self._response_task = None

    def _is_current(self, generation: int) -> bool:
        return not self._closed and generation == self._generation_id

    async def _emit(
        self,
        event_type: str,
        *,
        generation_id: int | None = None,
        allow_stale: bool = False,
        **payload: Any,
    ) -> None:
        generation = (
            self._generation_id if generation_id is None else generation_id
        )
        if not allow_stale and not self._is_current(generation):
            return
        event = {
            "type": event_type,
            "sessionId": self.session_id,
            "generationId": generation,
            **payload,
        }
        async with self._send_lock:
            await self._send_event(event)

    def _validate_audio_size(self, audio_base64: str) -> None:
        estimated_bytes = (len(audio_base64) * 3) // 4
        if estimated_bytes > self._config.max_audio_message_bytes:
            raise ValueError(
                "audio.append exceeds VOICE_MAX_AUDIO_MESSAGE_BYTES"
            )
