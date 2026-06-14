"use client";

import type {
  Citation,
  ConversationTurn,
  VoiceState,
} from "@insurance/contracts";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { useCustomerVoiceSession } from "../../lib/audio/use-customer-voice-session";
import {
  ChevronIcon,
  DocumentIcon,
  MicIcon,
  PhoneOffIcon,
  SendIcon,
  ShieldIcon,
} from "./icons";
import styles from "./customer-call-room.module.css";

type CustomerCallRoomProps = {
  sessionId: string;
  customerName?: string;
  productName?: string;
};

const STATE_COPY: Record<VoiceState, { title: string; detail: string }> = {
  IDLE: {
    title: "Ready when you are",
    detail: "Start a voice conversation about this policy",
  },
  CONNECTING: {
    title: "Joining the call",
    detail: "Setting up a secure audio connection",
  },
  LISTENING: {
    title: "I’m listening",
    detail: "Speak naturally — you can pause at any time",
  },
  FINALIZING_TRANSCRIPT: {
    title: "Got that",
    detail: "Preparing your question",
  },
  RETRIEVING: {
    title: "Checking the policy PDF",
    detail: "Looking only at the uploaded product document",
  },
  GENERATING: {
    title: "Putting it clearly",
    detail: "Preparing a grounded product explanation",
  },
  SPEAKING: {
    title: "Your advisor is speaking",
    detail: "Please wait for them to finish, then it's your turn",
  },
  AWAITING_CALLBACK_CONFIRMATION: {
    title: "One final choice",
    detail: "Review the callback offer",
  },
  ENDING: {
    title: "Wrapping up",
    detail: "Saving your conversation",
  },
  ERROR: {
    title: "Voice is unavailable",
    detail: "You can continue by typing below",
  },
};

const SUGGESTED_QUESTIONS = [
  "What are the main benefits of this policy?",
  "Who is this policy meant for?",
  "Are there any waiting periods or exclusions?",
];

function CitationPills({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;

  return (
    <div className={styles.citationRow} aria-label="Answer sources">
      {citations.map((citation) => (
        <details className={styles.citation} key={citation.id}>
          <summary>
            <DocumentIcon width={13} height={13} />
            Page {citation.pageNumber}
          </summary>
          <div className={styles.citationPanel}>
            <strong>
              {citation.sectionHeading || citation.filename}
            </strong>
            {citation.passage}
          </div>
        </details>
      ))}
    </div>
  );
}

function ConversationItem({ turn }: { turn: ConversationTurn }) {
  const customer = turn.role === "customer";

  return (
    <article
      className={`${styles.turn} ${customer ? styles.turnCustomer : ""}`}
    >
      <div className={styles.avatar}>{customer ? "Y" : "A"}</div>
      <div>
        <div className={styles.speaker}>
          {customer ? "You" : "Policy advisor"}
        </div>
        <p className={styles.turnText}>{turn.text}</p>
        <CitationPills citations={turn.citations} />
      </div>
    </article>
  );
}

export function CustomerCallRoom({
  sessionId,
  customerName = "there",
  productName = "your insurance plan",
}: CustomerCallRoomProps) {
  const [text, setText] = useState("");
  const timelineRef = useRef<HTMLDivElement>(null);
  const {
    voiceState,
    turns,
    partialTranscript,
    agentDraft,
    citations,
    callbackProposal,
    lead,
    error,
    microphoneDenied,
    connect,
    end,
    submitText,
    confirmCallback,
    cancelCallback,
  } = useCustomerVoiceSession({ sessionId });

  const isCallActive = voiceState !== "IDLE" && voiceState !== "ENDING";
  const isBusy =
    voiceState === "CONNECTING" ||
    voiceState === "RETRIEVING" ||
    voiceState === "GENERATING";
  const status = STATE_COPY[voiceState];
  const displayName = useMemo(
    () => customerName.trim().split(/\s+/)[0] || "there",
    [customerName],
  );

  useEffect(() => {
    timelineRef.current?.scrollTo({
      top: timelineRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns, partialTranscript, agentDraft]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitText(text);
    setText("");
  }

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <a className={styles.brand} href="/customer" aria-label="Assure home">
          <span className={styles.brandMark}>
            <ShieldIcon width={19} height={19} />
          </span>
          <span className={styles.brandName}>Assure</span>
        </a>
        <div className={styles.secureNote}>
          <ShieldIcon width={15} height={15} />
          <span>PDF-grounded insurance advisor</span>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.conversation}>
          <p className={styles.eyebrow}>Insurance product advisor</p>
          <h1 className={styles.title}>
            Hello, {displayName}. Let’s see whether this plan <em>fits.</em>
          </h1>
          <p className={styles.intro}>
            Your advisor starts with a short overview of {productName}, then
            answers your questions only from the uploaded policy document and
            shows where each answer came from.
          </p>

          <div className={styles.statusBar} aria-live="polite">
            <div
              className={styles.statusOrb}
              data-active={isCallActive || undefined}
            >
              <MicIcon width={16} height={16} />
            </div>
            <div className={styles.statusCopy}>
              <strong>{status.title}</strong>
              <span>{status.detail}</span>
            </div>
          </div>

          {error ? (
            <div className={styles.errorBanner} role="alert">
              <span>{error.message}</span>
            </div>
          ) : null}

          {lead?.callbackStatus === "requested" ? (
            <div className={styles.successBanner} role="status">
              <ShieldIcon width={16} height={16} />
              Your callback request has been shared with the insurance team.
            </div>
          ) : null}

          <div className={styles.timeline} ref={timelineRef}>
            {!turns.length && !partialTranscript && !agentDraft ? (
              <div className={styles.emptyConversation}>
                <p>Your conversation will appear here as you speak.</p>
              </div>
            ) : null}

            {turns.map((turn) => (
              <ConversationItem key={turn.id} turn={turn} />
            ))}

            {partialTranscript ? (
              <article
                className={`${styles.turn} ${styles.turnCustomer} ${styles.draft}`}
              >
                <div className={styles.avatar}>Y</div>
                <div>
                  <div className={styles.speaker}>You · listening</div>
                  <p className={styles.turnText}>
                    {partialTranscript}
                    <span className={styles.cursor} />
                  </p>
                </div>
              </article>
            ) : null}

            {agentDraft ? (
              <article className={`${styles.turn} ${styles.draft}`}>
                <div className={styles.avatar}>A</div>
                <div>
                  <div className={styles.speaker}>Policy advisor</div>
                  <p className={styles.turnText}>
                    {agentDraft}
                    <span className={styles.cursor} />
                  </p>
                  <CitationPills citations={citations} />
                </div>
              </article>
            ) : null}
          </div>

          <form className={styles.composer} onSubmit={handleSubmit}>
            {isCallActive ? (
              <button
                className={styles.endButton}
                type="button"
                onClick={() => void end()}
              >
                <PhoneOffIcon />
                End call
              </button>
            ) : (
              <button
                className={styles.callButton}
                type="button"
                onClick={() => void connect()}
              >
                <MicIcon />
                Start conversation
              </button>
            )}
            <input
              className={styles.textInput}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder={
                microphoneDenied
                  ? "Microphone unavailable — type your policy question"
                  : "Or type a policy question…"
              }
              aria-label="Type an insurance question"
            />
            <button
              className={styles.sendButton}
              type="submit"
              disabled={!text.trim() || isBusy}
              aria-label="Send question"
            >
              <SendIcon width={17} height={17} />
            </button>
          </form>
        </section>

        <aside className={styles.aside}>
          <div className={styles.asideTop}>
            <div className={styles.advisor}>
              <div className={styles.advisorPortrait}>
                A
                <span className={styles.onlineDot} />
              </div>
              <div>
                <p className={styles.advisorName}>AI policy advisor</p>
                <p className={styles.advisorRole}>Policy sales guidance · English</p>
              </div>
            </div>

            <h2 className={styles.asideHeading}>
              A clearer way to evaluate this policy.
            </h2>
            <p className={styles.asideCopy}>
              You will hear a short product introduction first. After that, ask
              about benefits, claims, exclusions, or waiting periods and get
              grounded answers from the insurer’s uploaded PDF.
            </p>

            <div className={styles.promptList}>
              {SUGGESTED_QUESTIONS.map((question) => (
                <button
                  className={styles.prompt}
                  type="button"
                  key={question}
                  onClick={() => {
                    if (!isCallActive) void connect();
                    setText(question);
                  }}
                >
                  <ChevronIcon />
                  {question}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.asideBottom}>
            <div className={styles.disclosure}>
              <ShieldIcon width={15} height={15} />
              <span>
                You are speaking with an AI-generated voice. This service
                explains the uploaded insurance document and does not provide
                financial advice. When you finish, you can choose whether to
                request a callback.
              </span>
            </div>
          </div>
        </aside>
      </main>

      {callbackProposal ? (
        <section
          className={styles.proposal}
          role="dialog"
          aria-modal="true"
          aria-labelledby="callback-title"
        >
          <p className={styles.proposalLabel}>Before you go</p>
          <h2 id="callback-title">Would you like a callback from our insurance team?</h2>
          <p>{callbackProposal.reason}</p>
          {callbackProposal.preferredCallbackText ? (
            <p className={styles.proposalTime}>
              Preferred time:{" "}
              <strong>{callbackProposal.preferredCallbackText}</strong>
            </p>
          ) : null}
          <div className={styles.proposalActions}>
            <button
              className={`${styles.proposalButton} ${styles.proposalButtonSecondary}`}
              type="button"
              onClick={() => void cancelCallback()}
            >
              Not now
            </button>
            <button
              className={styles.proposalButton}
              type="button"
              onClick={() => void confirmCallback()}
            >
              Request callback
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
