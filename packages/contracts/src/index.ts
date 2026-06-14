export type CallbackStatus =
  | "not_requested"
  | "requested"
  | "in_progress"
  | "completed"
  | "cancelled";

export type CallbackSource =
  | "customer_voice"
  | "customer_ui"
  | "salesperson";

export type SessionStatus = "active" | "completed" | "abandoned";

export type Lead = {
  id: string;
  sessionId: string;
  customerName: string | null;
  phone: string | null;
  productId: string;
  callbackStatus: CallbackStatus;
  callbackReason: string | null;
  preferredCallbackText: string | null;
  preferredCallbackAt: string | null;
  conversationSummary: string | null;
  createdAt: string;
  updatedAt: string;
};

export type AuditEvent = {
  id: string;
  leadId: string;
  eventType: string;
  source: CallbackSource;
  payload: Record<string, unknown>;
  createdAt: string;
};

export type Citation = {
  id: string;
  documentId: string;
  filename: string;
  pageNumber: number;
  sectionHeading: string | null;
  passage: string;
};

export type ConversationTurn = {
  id: string;
  sessionId: string;
  role: "customer" | "agent";
  text: string;
  citations: Citation[];
  createdAt: string;
};

export type VoiceState =
  | "IDLE"
  | "CONNECTING"
  | "LISTENING"
  | "FINALIZING_TRANSCRIPT"
  | "RETRIEVING"
  | "GENERATING"
  | "SPEAKING"
  | "AWAITING_CALLBACK_CONFIRMATION"
  | "ENDING"
  | "ERROR";

export type CallbackUpdate = {
  status: CallbackStatus;
  reason?: string | null;
  preferredCallbackText?: string | null;
  preferredCallbackAt?: string | null;
  source: CallbackSource;
};

export type ClientVoiceEvent =
  | { type: "session.start"; sessionId: string }
  | { type: "audio.append"; sessionId: string; audio: string }
  | { type: "audio.commit"; sessionId: string }
  | { type: "response.cancel"; sessionId: string; generationId: number }
  | { type: "session.end"; sessionId: string };

type GenerationEvent = {
  sessionId: string;
  generationId: number;
};

export type ServerVoiceEvent =
  | ({ type: "session.ready" } & GenerationEvent)
  | ({ type: "transcript.partial"; text: string } & GenerationEvent)
  | ({ type: "transcript.final"; text: string } & GenerationEvent)
  | ({ type: "agent.text.delta"; delta: string } & GenerationEvent)
  | ({ type: "agent.text.complete"; text: string } & GenerationEvent)
  | ({ type: "agent.audio.chunk"; audio: string } & GenerationEvent)
  | ({ type: "agent.response.cancelled" } & GenerationEvent)
  | ({ type: "citation.created"; citation: Citation } & GenerationEvent)
  | ({
      type: "callback.proposed";
      actionId: string;
      reason: string;
      preferredCallbackText: string | null;
      expiresAt: string;
    } & GenerationEvent)
  | ({ type: "callback.updated"; lead: Lead } & GenerationEvent)
  | ({
      type: "session.error";
      code: string;
      message: string;
      recoverable: boolean;
    } & GenerationEvent);
