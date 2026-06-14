"use client";

import type {
  Citation,
  ClientVoiceEvent,
  ConversationTurn,
  Lead,
  ServerVoiceEvent,
  VoiceState,
} from "@insurance/contracts";
import { useCallback, useEffect, useRef, useState } from "react";

import { MicrophoneCapture } from "./microphone";
import { StreamingAudioPlayer } from "./playback";
import { SpeechFallbackPlayer } from "./speech-fallback";

type CallbackProposal = {
  actionId: string;
  reason: string;
  preferredCallbackText: string | null;
  expiresAt: string;
};

type SessionError = {
  code: string;
  message: string;
  recoverable: boolean;
};

type TextSubmitEvent = {
  type: "text.submit";
  sessionId: string;
  text: string;
};

type UseCustomerVoiceSessionOptions = {
  sessionId: string;
  initialTurns?: ConversationTurn[];
};

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";
const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "") ??
  "ws://localhost:8000";
const OPENING_PITCH_TRIGGER = "__OPENING_PITCH__";
const END_CALLBACK_TRIGGER = "__END_CALLBACK__";
const PREFER_BROWSER_SPEECH = false;

function createLocalTurn(
  sessionId: string,
  role: ConversationTurn["role"],
  text: string,
  citations: Citation[] = [],
): ConversationTurn {
  return {
    id: crypto.randomUUID(),
    sessionId,
    role,
    text,
    citations,
    createdAt: new Date().toISOString(),
  };
}

export function useCustomerVoiceSession({
  sessionId,
  initialTurns = [],
}: UseCustomerVoiceSessionOptions) {
  const [voiceState, setVoiceState] = useState<VoiceState>("IDLE");
  const [turns, setTurns] = useState<ConversationTurn[]>(initialTurns);
  const [partialTranscript, setPartialTranscript] = useState("");
  const [agentDraft, setAgentDraft] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [callbackProposal, setCallbackProposal] =
    useState<CallbackProposal | null>(null);
  const [lead, setLead] = useState<Lead | null>(null);
  const [error, setError] = useState<SessionError | null>(null);
  const [microphoneDenied, setMicrophoneDenied] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const microphoneRef = useRef(new MicrophoneCapture());
  const playerRef = useRef(new StreamingAudioPlayer());
  const speechFallbackRef = useRef(new SpeechFallbackPlayer());
  const generationRef = useRef(0);
  const agentDraftRef = useRef("");
  const citationsRef = useRef<Citation[]>([]);
  const speakingRef = useRef(false);
  const audioChunkCountRef = useRef(0);
  const introRequestedRef = useRef(false);
  const callbackOfferedRef = useRef(false);
  const audioFallbackTriggeredRef = useRef(false);
  // Half-duplex gate: true while the agent is preparing or speaking a response.
  // While true the mic is NOT streamed to STT, so the agent never transcribes
  // its own audio or room noise during its turn (which would otherwise trigger
  // spurious "questions" that cancel the in-flight response).
  const agentBusyRef = useRef(false);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const markAgentBusy = useCallback(() => {
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current);
      idleTimerRef.current = null;
    }
    agentBusyRef.current = true;
  }, []);

  const releaseAgentAfterPlayback = useCallback(() => {
    // Re-open the mic once the agent's audio has fully drained, plus a short
    // tail to let the speaker output decay so it isn't captured as input.
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    const waitMs = playerRef.current.getRemainingMs() + 400;
    idleTimerRef.current = setTimeout(() => {
      idleTimerRef.current = null;
      agentBusyRef.current = false;
      speakingRef.current = false;
      microphoneRef.current.setAgentSpeaking(false);
      setVoiceState("LISTENING");
    }, waitMs);
  }, []);

  const releaseAgentNow = useCallback(() => {
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current);
      idleTimerRef.current = null;
    }
    agentBusyRef.current = false;
    speakingRef.current = false;
    microphoneRef.current.setAgentSpeaking(false);
  }, []);

  const send = useCallback((event: ClientVoiceEvent | TextSubmitEvent) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(event));
    }
  }, []);

  const submitSystemText = useCallback(
    (text: string) => {
      // System-triggered agent turns (opening pitch, end-of-call callback offer)
      // gate the mic so the agent's own audio isn't transcribed mid-turn.
      markAgentBusy();
      send({ type: "text.submit", sessionId, text });
    },
    [markAgentBusy, send, sessionId],
  );

  const interrupt = useCallback(() => {
    if (!speakingRef.current) return;

    const interruptedGeneration = generationRef.current;
    generationRef.current += 1;
    // Clear the half-duplex gate so the customer's CONTINUING barge-in speech
    // now flows to STT (releaseAgentNow also stops agent-speaking mode + idle
    // timer + speakingRef).
    releaseAgentNow();
    playerRef.current.setGeneration(generationRef.current);
    speechFallbackRef.current.stop({
      onEnd: () => {
        speakingRef.current = false;
        setVoiceState("LISTENING");
      },
    });
    audioChunkCountRef.current = 0;
    setAgentDraft("");
    agentDraftRef.current = "";
    citationsRef.current = [];
    setCitations([]);
    setVoiceState("LISTENING");
    send({
      type: "response.cancel",
      sessionId,
      generationId: interruptedGeneration,
    });
  }, [releaseAgentNow, send, sessionId]);

  const handleEvent = useCallback(
    (event: ServerVoiceEvent) => {
      if (event.sessionId !== sessionId) return;
      if (event.generationId < generationRef.current) return;

      if (event.generationId > generationRef.current) {
        generationRef.current = event.generationId;
        playerRef.current.setGeneration(event.generationId);
        microphoneRef.current.setAgentSpeaking(false);
        speechFallbackRef.current.stop({
          onEnd: () => {
            speakingRef.current = false;
          },
        });
        audioChunkCountRef.current = 0;
        audioFallbackTriggeredRef.current = false;
        agentDraftRef.current = "";
        citationsRef.current = [];
        setAgentDraft("");
        setCitations([]);
      }

      switch (event.type) {
        case "session.ready":
          setVoiceState("LISTENING");
          if (!introRequestedRef.current && !turns.length) {
            introRequestedRef.current = true;
            submitSystemText(OPENING_PITCH_TRIGGER);
          }
          break;
        case "transcript.partial":
          setVoiceState("LISTENING");
          setPartialTranscript(event.text);
          break;
        case "transcript.final":
          markAgentBusy();
          setPartialTranscript("");
          setVoiceState("RETRIEVING");
          setTurns((current) => [
            ...current,
            createLocalTurn(sessionId, "customer", event.text),
          ]);
          break;
        case "agent.text.delta":
          setVoiceState("GENERATING");
          agentDraftRef.current += event.delta;
          setAgentDraft(agentDraftRef.current);
          break;
        case "citation.created":
          citationsRef.current = [...citationsRef.current, event.citation];
          setCitations(citationsRef.current);
          break;
        case "agent.text.complete": {
          const finalText = event.text || agentDraftRef.current;
          setTurns((current) => [
            ...current,
            createLocalTurn(
              sessionId,
              "agent",
              finalText,
              citationsRef.current,
            ),
          ]);
          agentDraftRef.current = "";
          citationsRef.current = [];
          setAgentDraft("");
          setCitations([]);
          if (PREFER_BROWSER_SPEECH || audioChunkCountRef.current === 0) {
            playerRef.current.stop();
            speechFallbackRef.current.speak(finalText, {
              onStart: () => {
                speakingRef.current = true;
                microphoneRef.current.setAgentSpeaking(true);
                setVoiceState("SPEAKING");
              },
              onEnd: () => {
                releaseAgentNow();
                setVoiceState("LISTENING");
              },
            });
          } else {
            // Real (Deepgram) audio path: all chunks are already enqueued by the
            // time text.complete arrives, so re-open the mic once they drain.
            releaseAgentAfterPlayback();
          }
          break;
        }
        case "agent.audio.chunk":
          audioChunkCountRef.current += 1;
          if (!PREFER_BROWSER_SPEECH) {
            speakingRef.current = true;
            microphoneRef.current.setAgentSpeaking(true);
            setVoiceState("SPEAKING");
            void playerRef.current.enqueue(event.audio, event.generationId).catch(() => {
              if (audioFallbackTriggeredRef.current) return;
              audioFallbackTriggeredRef.current = true;
              speechFallbackRef.current.speak(agentDraftRef.current || "I’m sorry, I could not play the audio response.", {
                onStart: () => {
                  speakingRef.current = true;
                  microphoneRef.current.setAgentSpeaking(true);
                  setVoiceState("SPEAKING");
                },
                onEnd: () => {
                  speakingRef.current = false;
                  microphoneRef.current.setAgentSpeaking(false);
                  setVoiceState("LISTENING");
                },
              });
            });
          }
          break;
        case "agent.response.cancelled":
          releaseAgentNow();
          speechFallbackRef.current.stop({
            onEnd: () => {
              speakingRef.current = false;
            },
          });
          setVoiceState("LISTENING");
          break;
        case "callback.proposed":
          callbackOfferedRef.current = true;
          setCallbackProposal({
            actionId: event.actionId,
            reason: event.reason,
            preferredCallbackText: event.preferredCallbackText,
            expiresAt: event.expiresAt,
          });
          setVoiceState("AWAITING_CALLBACK_CONFIRMATION");
          break;
        case "callback.updated":
          setLead(event.lead);
          setCallbackProposal(null);
          setVoiceState("LISTENING");
          break;
        case "session.error":
          releaseAgentNow();
          setError({
            code: event.code,
            message: event.message,
            recoverable: event.recoverable,
          });
          setVoiceState("ERROR");
          break;
      }
    },
    [sessionId, submitSystemText, turns.length],
  );

  const connect = useCallback(async () => {
    if (socketRef.current) return;

    setError(null);
    setVoiceState("CONNECTING");
    // Unlock the playback AudioContext now, while the user's click is still on
    // the call stack — otherwise Chrome blocks audio that first touches the
    // context from the later (async) WebSocket message handler.
    audioFallbackTriggeredRef.current = false;
    void playerRef.current.prime();
    // The agent opens with a pitch, so start in the "busy" (not listening)
    // state — the mic stays muted until the pitch finishes playing.
    agentBusyRef.current = true;
    const socket = new WebSocket(
      `${WS_URL}/ws/voice/${encodeURIComponent(sessionId)}`,
    );
    socketRef.current = socket;

    socket.onopen = async () => {
      send({ type: "session.start", sessionId });
      try {
        await microphoneRef.current.start({
          // Half-duplex: only stream the mic to STT while the agent is NOT
          // talking. This prevents the agent's own audio and room noise from
          // being transcribed mid-turn and cancelling its response.
          onAudio: (audio) => {
            if (agentBusyRef.current) return;
            send({ type: "audio.append", sessionId, audio });
          },
          onVoiceEnd: () => {
            if (agentBusyRef.current) return;
            send({ type: "audio.commit", sessionId });
          },
          // Barge-in intentionally DISABLED — voice-activated interruption was
          // destabilizing the turn/generation state (lost transcripts, resets).
          // Reverted to stable half-duplex turn-by-turn. The barge-in detector
          // in microphone.ts stays dormant (it only fires if onBargeIn is wired).
          // To re-enable later: add `onBargeIn: () => interrupt()` here.
        });
      } catch {
        setMicrophoneDenied(true);
        agentBusyRef.current = false;
        setVoiceState("LISTENING");
      }
    };

    socket.onmessage = (message) => {
      try {
        handleEvent(JSON.parse(message.data as string) as ServerVoiceEvent);
      } catch {
        setError({
          code: "INVALID_EVENT",
          message: "The voice connection returned an unreadable event.",
          recoverable: true,
        });
      }
    };

    socket.onerror = () => {
      setError({
        code: "VOICE_CONNECTION_FAILED",
        message: "We could not connect the call. Text chat is still available.",
        recoverable: true,
      });
      setVoiceState("ERROR");
    };

    socket.onclose = () => {
      socketRef.current = null;
      speakingRef.current = false;
      setVoiceState((current) =>
        current === "ENDING" ? "IDLE" : current === "IDLE" ? current : "ERROR",
      );
    };
  }, [handleEvent, send, sessionId]);

  const end = useCallback(async () => {
    const shouldOfferCallback =
      turns.some((turn) => turn.role === "agent") &&
      !callbackOfferedRef.current &&
      lead?.callbackStatus !== "requested";
    if (shouldOfferCallback) {
      callbackOfferedRef.current = true;
      setVoiceState("RETRIEVING");
      submitSystemText(END_CALLBACK_TRIGGER);
      return;
    }
    setVoiceState("ENDING");
    releaseAgentNow();
    send({ type: "session.end", sessionId });
    playerRef.current.stop();
    speechFallbackRef.current.stop({
      onEnd: () => {
        speakingRef.current = false;
      },
    });
    speakingRef.current = false;
    await microphoneRef.current.stop();
    socketRef.current?.close(1000, "Customer ended the call");
    socketRef.current = null;
    setVoiceState("IDLE");
  }, [lead?.callbackStatus, releaseAgentNow, send, sessionId, submitSystemText, turns]);

  const submitText = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      markAgentBusy();
      setTurns((current) => [
        ...current,
        createLocalTurn(sessionId, "customer", trimmed),
      ]);
      setVoiceState("RETRIEVING");
      send({ type: "text.submit", sessionId, text: trimmed });
    },
    [markAgentBusy, send, sessionId],
  );

  const resolveCallback = useCallback(
    async (decision: "confirm" | "cancel") => {
      if (!callbackProposal) return;

      const response = await fetch(
        `${API_URL}/api/callback-actions/${callbackProposal.actionId}/${decision}`,
        { method: "POST" },
      );

      if (!response.ok) {
        setError({
          code: "CALLBACK_UPDATE_FAILED",
          message: "The callback preference could not be saved. Please retry.",
          recoverable: true,
        });
        return;
      }

      if (decision === "confirm") {
        const data = (await response.json()) as Lead | { lead: Lead };
        setLead("lead" in data ? data.lead : data);
      }
      callbackOfferedRef.current = true;
      setCallbackProposal(null);
      setVoiceState("LISTENING");
    },
    [callbackProposal],
  );

  useEffect(() => {
    const handlePageHide = () => {
      if (socketRef.current) {
        navigator.sendBeacon(
          `${API_URL}/api/sessions/${encodeURIComponent(sessionId)}/end`,
          new Blob([JSON.stringify({ status: "abandoned" })], {
            type: "application/json",
          }),
        );
      }
    };
    window.addEventListener("pagehide", handlePageHide);

    return () => {
      window.removeEventListener("pagehide", handlePageHide);
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      socketRef.current?.close();
      void microphoneRef.current.stop();
      void playerRef.current.close();
      speechFallbackRef.current.stop({
        onEnd: () => {
          speakingRef.current = false;
        },
      });
    };
  }, [sessionId]);

  return {
    voiceState,
    turns,
    partialTranscript,
    agentDraft,
    citations,
    callbackProposal,
    lead,
    error,
    microphoneDenied,
    generationId: generationRef.current,
    connect,
    end,
    interrupt,
    submitText,
    confirmCallback: () => resolveCallback("confirm"),
    cancelCallback: () => resolveCallback("cancel"),
  };
}
