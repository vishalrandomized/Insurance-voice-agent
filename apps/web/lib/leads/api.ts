import type {
  AuditEvent,
  CallbackStatus,
  CallbackUpdate,
  Citation,
  ConversationTurn,
  Lead,
} from "@insurance/contracts";

export type LeadWithActivity = Lead & {
  productName?: string;
  turns?: ConversationTurn[];
  auditEvents?: AuditEvent[];
};

export type LeadFilters = {
  status: CallbackStatus | "all";
  query: string;
};

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

type WireLead = Partial<LeadWithActivity> & {
  session_id?: string;
  customer_name?: string | null;
  product_id?: string;
  product_name?: string;
  callback_status?: CallbackStatus;
  callback_reason?: string | null;
  preferred_callback_text?: string | null;
  preferred_callback_at?: string | null;
  conversation_summary?: string | null;
  created_at?: string;
  updated_at?: string;
  conversation_turns?: ConversationTurn[];
  audit_events?: AuditEvent[];
};

type WireAuditEvent = Partial<AuditEvent> & {
  lead_id?: string;
  event_type?: string;
  created_at?: string;
};

type WireCitation = Partial<Citation> & {
  document_id?: string;
  page_number?: number;
  section_heading?: string | null;
};

type WireTurn = Partial<ConversationTurn> & {
  session_id?: string;
  created_at?: string;
  citations?: WireCitation[];
};

function normalizeCitation(citation: WireCitation): Citation {
  return {
    id: citation.id ?? crypto.randomUUID(),
    documentId: citation.documentId ?? citation.document_id ?? "",
    filename: citation.filename ?? "Insurance product document",
    pageNumber: citation.pageNumber ?? citation.page_number ?? 0,
    sectionHeading:
      citation.sectionHeading ?? citation.section_heading ?? null,
    passage: citation.passage ?? "",
  };
}

function normalizeTurn(turn: WireTurn): ConversationTurn {
  return {
    id: turn.id ?? crypto.randomUUID(),
    sessionId: turn.sessionId ?? turn.session_id ?? "",
    role: turn.role ?? "customer",
    text: turn.text ?? "",
    citations: (turn.citations ?? []).map(normalizeCitation),
    createdAt: turn.createdAt ?? turn.created_at ?? new Date().toISOString(),
  };
}

function normalizeAuditEvent(event: WireAuditEvent): AuditEvent {
  return {
    id: event.id ?? crypto.randomUUID(),
    leadId: event.leadId ?? event.lead_id ?? "",
    eventType: event.eventType ?? event.event_type ?? "activity_recorded",
    source: event.source ?? "salesperson",
    payload: event.payload ?? {},
    createdAt: event.createdAt ?? event.created_at ?? new Date().toISOString(),
  };
}

function normalizeLead(lead: WireLead): LeadWithActivity {
  return {
    id: lead.id ?? "",
    sessionId: lead.sessionId ?? lead.session_id ?? "",
    customerName: lead.customerName ?? lead.customer_name ?? null,
    phone: lead.phone ?? null,
    productId: lead.productId ?? lead.product_id ?? "",
    productName: lead.productName ?? lead.product_name,
    callbackStatus:
      lead.callbackStatus ?? lead.callback_status ?? "not_requested",
    callbackReason: lead.callbackReason ?? lead.callback_reason ?? null,
    preferredCallbackText:
      lead.preferredCallbackText ?? lead.preferred_callback_text ?? null,
    preferredCallbackAt:
      lead.preferredCallbackAt ?? lead.preferred_callback_at ?? null,
    conversationSummary:
      lead.conversationSummary ?? lead.conversation_summary ?? null,
    createdAt: lead.createdAt ?? lead.created_at ?? new Date().toISOString(),
    updatedAt: lead.updatedAt ?? lead.updated_at ?? new Date().toISOString(),
    turns: (lead.turns ?? lead.conversation_turns)?.map(normalizeTurn),
    auditEvents: (lead.auditEvents ?? lead.audit_events)?.map(
      normalizeAuditEvent,
    ),
  };
}

function normalizeList(payload: unknown): LeadWithActivity[] {
  if (Array.isArray(payload)) return payload.map((lead) => normalizeLead(lead));
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    const list = record.leads ?? record.items ?? record.data;
    if (Array.isArray(list)) return list.map((lead) => normalizeLead(lead));
  }
  return [];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const message = await response.text().catch(() => "");
    throw new Error(message || `Request failed (${response.status})`);
  }

  return response.json() as Promise<T>;
}

export async function getLeads(): Promise<LeadWithActivity[]> {
  return normalizeList(await request<unknown>("/api/leads"));
}

export async function getLead(leadId: string): Promise<LeadWithActivity> {
  const initialLeadPayload = await request<WireLead | { lead: WireLead }>(
    `/api/leads/${leadId}`,
  );
  const initialWireLead =
    "lead" in initialLeadPayload
      ? initialLeadPayload.lead
      : (initialLeadPayload as WireLead);
  const initialLead = normalizeLead(initialWireLead);

  const [auditPayload, sessionPayload] = await Promise.all([
    request<
      WireAuditEvent[] | {
        events?: WireAuditEvent[];
        auditEvents?: WireAuditEvent[];
        audit_events?: WireAuditEvent[];
      }
    >(`/api/leads/${leadId}/audit-events`).catch(
      () => [] as WireAuditEvent[],
    ),
    initialLead.sessionId
      ? request<
          | { turns?: WireTurn[]; conversation_turns?: WireTurn[] }
          | WireTurn[]
        >(`/api/sessions/${initialLead.sessionId}`).catch(() => null)
      : Promise.resolve(null),
  ]);

  const wireAuditEvents = Array.isArray(auditPayload)
    ? auditPayload
    : auditPayload.events ??
      auditPayload.auditEvents ??
      auditPayload.audit_events ??
      [];
  const sessionTurns = Array.isArray(sessionPayload)
    ? sessionPayload
    : sessionPayload?.turns ?? sessionPayload?.conversation_turns ?? [];

  return {
    ...initialLead,
    turns: initialLead.turns?.length
      ? initialLead.turns
      : sessionTurns.map(normalizeTurn),
    auditEvents: wireAuditEvents.map(normalizeAuditEvent),
  };
}

export async function updateCallbackStatus(
  leadId: string,
  status: CallbackStatus,
  current: LeadWithActivity,
): Promise<LeadWithActivity> {
  const body: CallbackUpdate = {
    status,
    reason: current.callbackReason,
    preferredCallbackText: current.preferredCallbackText,
    preferredCallbackAt: current.preferredCallbackAt,
    source: "salesperson",
  };

  const payload = await request<
    WireLead | { lead: WireLead }
  >(`/api/leads/${leadId}/callback`, {
    method: "PATCH",
    body: JSON.stringify({
      status: body.status,
      reason: body.reason,
      preferred_callback_text: body.preferredCallbackText,
      preferred_callback_at: body.preferredCallbackAt,
      source: body.source,
    }),
  });

  return normalizeLead("lead" in payload ? payload.lead : payload);
}

export function filterLeads(
  leads: LeadWithActivity[],
  filters: LeadFilters,
): LeadWithActivity[] {
  const query = filters.query.trim().toLowerCase();
  return leads
    .filter(
      (lead) =>
        filters.status === "all" || lead.callbackStatus === filters.status,
    )
    .filter((lead) => {
      if (!query) return true;
      return [
        lead.customerName,
        lead.phone,
        lead.productName,
        lead.callbackReason,
        lead.conversationSummary,
      ].some((value) => value?.toLowerCase().includes(query));
    })
    .sort((a, b) => {
      const rank: Record<CallbackStatus, number> = {
        requested: 0,
        in_progress: 1,
        not_requested: 2,
        completed: 3,
        cancelled: 4,
      };
      return (
        rank[a.callbackStatus] - rank[b.callbackStatus] ||
        Date.parse(b.updatedAt) - Date.parse(a.updatedAt)
      );
    });
}

const now = Date.now();
const iso = (minutesAgo: number) =>
  new Date(now - minutesAgo * 60_000).toISOString();

const familyCitation: Citation = {
  id: "citation-family",
  documentId: "doc-secure-family",
  filename: "SecureCare Family Protect.pdf",
  pageNumber: 12,
  sectionHeading: "Waiting periods",
  passage:
    "A waiting period of 30 days applies to all claims other than accidental injury. Named conditions are subject to a 24-month waiting period.",
};

export const demoLeads: LeadWithActivity[] = [
  {
    id: "lead-aanya",
    sessionId: "session-aanya",
    customerName: "Aanya Mehta",
    phone: "+91 98••• 48210",
    productId: "securecare-family",
    productName: "SecureCare Family Protect",
    callbackStatus: "requested",
    callbackReason: "Needs help comparing family floater coverage",
    preferredCallbackText: "Today after 5:30 PM",
    preferredCallbackAt: null,
    conversationSummary:
      "Aanya is evaluating family floater coverage for two adults and one child. Her main concerns are waiting periods, cashless hospitals, and adding a parent later.",
    createdAt: iso(49),
    updatedAt: iso(4),
    turns: [
      {
        id: "turn-a1",
        sessionId: "session-aanya",
        role: "customer",
        text: "Does the plan start covering illnesses immediately?",
        citations: [],
        createdAt: iso(21),
      },
      {
        id: "turn-a2",
        sessionId: "session-aanya",
        role: "agent",
        text: "The document states that most illness claims have a 30-day initial waiting period. Accidental injuries are excluded from that waiting period.",
        citations: [familyCitation],
        createdAt: iso(20),
      },
      {
        id: "turn-a3",
        sessionId: "session-aanya",
        role: "customer",
        text: "Please have someone call me so I can compare the family options.",
        citations: [],
        createdAt: iso(6),
      },
    ],
    auditEvents: [
      {
        id: "audit-a1",
        leadId: "lead-aanya",
        eventType: "callback_requested",
        source: "customer_voice",
        payload: { preferredCallbackText: "Today after 5:30 PM" },
        createdAt: iso(4),
      },
      {
        id: "audit-a2",
        leadId: "lead-aanya",
        eventType: "lead_created",
        source: "customer_ui",
        payload: {},
        createdAt: iso(49),
      },
    ],
  },
  {
    id: "lead-kabir",
    sessionId: "session-kabir",
    customerName: "Kabir Rao",
    phone: "+91 97••• 19034",
    productId: "health-shield",
    productName: "Health Shield Plus",
    callbackStatus: "in_progress",
    callbackReason: "Confirm room-rent limits and network hospital",
    preferredCallbackText: "Weekday mornings",
    preferredCallbackAt: null,
    conversationSummary:
      "Kabir wants an individual policy and is checking room eligibility and the cashless process before purchasing.",
    createdAt: iso(330),
    updatedAt: iso(38),
    turns: [],
    auditEvents: [
      {
        id: "audit-k1",
        leadId: "lead-kabir",
        eventType: "callback_status_changed",
        source: "salesperson",
        payload: { from: "requested", to: "in_progress" },
        createdAt: iso(38),
      },
    ],
  },
  {
    id: "lead-neelam",
    sessionId: "session-neelam",
    customerName: "Neelam Verma",
    phone: null,
    productId: "senior-assure",
    productName: "Senior Assure",
    callbackStatus: "not_requested",
    callbackReason: null,
    preferredCallbackText: null,
    preferredCallbackAt: null,
    conversationSummary:
      "Neelam asked about pre-existing condition waiting periods and domiciliary treatment. No callback was requested.",
    createdAt: iso(1440),
    updatedAt: iso(760),
    turns: [],
    auditEvents: [],
  },
  {
    id: "lead-arjun",
    sessionId: "session-arjun",
    customerName: "Arjun Nair",
    phone: "+91 99••• 66702",
    productId: "securecare-family",
    productName: "SecureCare Family Protect",
    callbackStatus: "completed",
    callbackReason: "Wanted premium illustration from an advisor",
    preferredCallbackText: "Yesterday evening",
    preferredCallbackAt: null,
    conversationSummary:
      "Arjun reviewed coverage limits and requested a premium illustration. The advisor callback has been completed.",
    createdAt: iso(2900),
    updatedAt: iso(1520),
    turns: [],
    auditEvents: [
      {
        id: "audit-r1",
        leadId: "lead-arjun",
        eventType: "callback_status_changed",
        source: "salesperson",
        payload: { from: "in_progress", to: "completed" },
        createdAt: iso(1520),
      },
    ],
  },
];
