"use client";

import { useEffect, useState } from "react";
import type {
  AuditEvent,
  CallbackStatus,
  Citation,
  ConversationTurn,
} from "@insurance/contracts";
import type { LeadWithActivity } from "../../lib/leads/api";
import { ClockIcon, CloseIcon, PhoneIcon, QuoteIcon } from "./icons";
import { StatusPill, statusLabels } from "./status-pill";
import styles from "./sales-dashboard.module.css";

const statuses: CallbackStatus[] = [
  "requested",
  "in_progress",
  "completed",
  "cancelled",
];

function displayDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function CitationCard({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);
  return (
    <button
      className={styles.citationCard}
      onClick={() => setOpen((current) => !current)}
      type="button"
    >
      <span className={styles.citationNumber}>p. {citation.pageNumber}</span>
      <span>
        <strong>{citation.sectionHeading ?? citation.filename}</strong>
        <small>{open ? citation.passage : "View supporting passage"}</small>
      </span>
      <span className={open ? styles.citationToggleOpen : styles.citationToggle}>
        +
      </span>
    </button>
  );
}

function Transcript({ turns }: { turns: ConversationTurn[] }) {
  if (!turns.length) {
    return (
      <div className={styles.sectionEmpty}>
        The transcript will appear here after the conversation is processed.
      </div>
    );
  }
  return (
    <div className={styles.transcript}>
      {turns.map((turn) => (
        <article className={styles.turn} key={turn.id}>
          <div className={styles.turnMeta}>
            <span
              className={
                turn.role === "agent"
                  ? styles.speakerAgent
                  : styles.speakerCustomer
              }
            >
              {turn.role === "agent" ? "AI advisor" : "Customer"}
            </span>
            <time>
              {new Intl.DateTimeFormat("en-IN", {
                hour: "2-digit",
                minute: "2-digit",
              }).format(new Date(turn.createdAt))}
            </time>
          </div>
          <p>{turn.text}</p>
          {turn.citations.length ? (
            <div className={styles.citations}>
              {turn.citations.map((citation) => (
                <CitationCard citation={citation} key={citation.id} />
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function AuditTimeline({ events }: { events: AuditEvent[] }) {
  if (!events.length) {
    return (
      <div className={styles.sectionEmpty}>
        No callback actions have been recorded.
      </div>
    );
  }
  return (
    <ol className={styles.timeline}>
      {[...events]
        .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))
        .map((event) => (
          <li key={event.id}>
            <span className={styles.timelineDot} />
            <div>
              <strong>
                {event.eventType
                  .replaceAll("_", " ")
                  .replace(/\b\w/g, (letter) => letter.toUpperCase())}
              </strong>
              <p>
                {event.source === "salesperson"
                  ? "Updated by sales team"
                  : "Captured from customer conversation"}
              </p>
              <time>{displayDate(event.createdAt)}</time>
            </div>
          </li>
        ))}
    </ol>
  );
}

export function LeadDetail({
  lead,
  loading,
  saving,
  saveError,
  onClose,
  onStatusChange,
}: {
  lead: LeadWithActivity | null;
  loading: boolean;
  saving: boolean;
  saveError: string | null;
  onClose: () => void;
  onStatusChange: (status: CallbackStatus) => void;
}) {
  const [tab, setTab] = useState<"conversation" | "activity">("conversation");

  useEffect(() => {
    setTab("conversation");
  }, [lead?.id]);

  if (!lead && !loading) {
    return (
      <aside className={styles.detailPlaceholder}>
        <div className={styles.placeholderGlyph}>↗</div>
        <p className={styles.eyebrow}>Lead intelligence</p>
        <h2>Select a conversation to review</h2>
        <p>
          Product-fit questions, grounded answers, callback context, and action
          history will appear here.
        </p>
      </aside>
    );
  }

  if (loading || !lead) {
    return (
      <aside className={styles.detailLoading} aria-label="Loading lead detail">
        <div />
        <div />
        <div />
      </aside>
    );
  }

  return (
    <aside className={styles.detailPanel}>
      <header className={styles.detailHeader}>
        <div>
          <p className={styles.eyebrow}>Lead profile</p>
          <h2>{lead.customerName ?? "Anonymous customer"}</h2>
        </div>
        <button
          aria-label="Close lead detail"
          className={styles.iconButton}
          onClick={onClose}
          type="button"
        >
          <CloseIcon />
        </button>
      </header>

      <div className={styles.detailScroll}>
        <section className={styles.callbackControl}>
          <div className={styles.callbackControlTop}>
            <div>
              <span>Callback workflow</span>
              <StatusPill status={lead.callbackStatus} />
            </div>
            {saving ? <span className={styles.savingLabel}>Saving…</span> : null}
          </div>
          <div className={styles.statusSelector}>
            {statuses.map((status) => (
              <button
                aria-pressed={lead.callbackStatus === status}
                disabled={saving}
                key={status}
                onClick={() => onStatusChange(status)}
                type="button"
              >
                <span />
                {statusLabels[status]}
              </button>
            ))}
          </div>
          {saveError ? (
            <p className={styles.inlineError} role="alert">
              {saveError} The previous status has been restored.
            </p>
          ) : null}
        </section>

        <section className={styles.contactGrid}>
          <div>
            <PhoneIcon />
            <span>
              <small>Phone</small>
              <strong>{lead.phone ?? "Not provided"}</strong>
            </span>
          </div>
          <div>
            <ClockIcon />
            <span>
              <small>Preferred time</small>
              <strong>{lead.preferredCallbackText ?? "No preference"}</strong>
            </span>
          </div>
        </section>

        <section className={styles.summaryBlock}>
          <div className={styles.sectionTitle}>
            <span>Conversation brief</span>
            <small>{lead.productName ?? lead.productId}</small>
          </div>
          <QuoteIcon />
          <p>
            {lead.conversationSummary ??
              "A summary has not been generated for this conversation yet."}
          </p>
          {lead.callbackReason ? (
            <div className={styles.intentCallout}>
              <small>Why they want a callback</small>
              <strong>{lead.callbackReason}</strong>
            </div>
          ) : null}
        </section>

        <nav className={styles.detailTabs} aria-label="Lead detail sections">
          <button
            className={tab === "conversation" ? styles.detailTabActive : ""}
            onClick={() => setTab("conversation")}
            type="button"
          >
            Conversation
            <span>{lead.turns?.length ?? 0}</span>
          </button>
          <button
            className={tab === "activity" ? styles.detailTabActive : ""}
            onClick={() => setTab("activity")}
            type="button"
          >
            Activity
            <span>{lead.auditEvents?.length ?? 0}</span>
          </button>
        </nav>

        {tab === "conversation" ? (
          <Transcript turns={lead.turns ?? []} />
        ) : (
          <AuditTimeline events={lead.auditEvents ?? []} />
        )}
      </div>
    </aside>
  );
}
