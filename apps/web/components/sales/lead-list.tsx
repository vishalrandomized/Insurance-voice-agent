"use client";

import type { CallbackStatus } from "@insurance/contracts";
import type { LeadWithActivity } from "../../lib/leads/api";
import { ChevronIcon, ClockIcon, PhoneIcon, SearchIcon } from "./icons";
import { StatusPill, statusLabels } from "./status-pill";
import styles from "./sales-dashboard.module.css";

type StatusFilter = CallbackStatus | "all";

function relativeTime(value: string) {
  const difference = Math.max(0, Date.now() - Date.parse(value));
  const minutes = Math.floor(difference / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function LeadList({
  leads,
  query,
  status,
  selectedId,
  onQueryChange,
  onStatusChange,
  onSelect,
}: {
  leads: LeadWithActivity[];
  query: string;
  status: StatusFilter;
  selectedId: string | null;
  onQueryChange: (value: string) => void;
  onStatusChange: (value: StatusFilter) => void;
  onSelect: (lead: LeadWithActivity) => void;
}) {
  const filters: Array<{ value: StatusFilter; label: string }> = [
    { value: "all", label: "All leads" },
    { value: "requested", label: "Requested" },
    { value: "in_progress", label: "In progress" },
    { value: "completed", label: "Completed" },
  ];

  return (
    <section className={styles.leadColumn} aria-label="Leads">
      <div className={styles.leadTools}>
        <label className={styles.searchBox}>
          <SearchIcon />
          <span className={styles.srOnly}>Search leads</span>
          <input
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search name, product, reason"
            type="search"
            value={query}
          />
          <kbd>⌘ K</kbd>
        </label>
        <div className={styles.filterRail} aria-label="Filter callback status">
          {filters.map((filter) => (
            <button
              className={status === filter.value ? styles.filterActive : ""}
              key={filter.value}
              onClick={() => onStatusChange(filter.value)}
              type="button"
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.listHeader}>
        <span>{leads.length} product conversations</span>
        <span>Newest activity</span>
      </div>

      <div className={styles.leadList}>
        {leads.length ? (
          leads.map((lead) => (
            <button
              className={`${styles.leadCard} ${
                selectedId === lead.id ? styles.leadCardSelected : ""
              }`}
              key={lead.id}
              onClick={() => onSelect(lead)}
              type="button"
            >
              <span className={styles.avatar}>
                {(lead.customerName ?? "Guest")
                  .split(" ")
                  .map((part) => part[0])
                  .slice(0, 2)
                  .join("")}
              </span>
              <span className={styles.leadCardBody}>
                <span className={styles.leadCardTopline}>
                  <strong>{lead.customerName ?? "Anonymous customer"}</strong>
                  <time>{relativeTime(lead.updatedAt)}</time>
                </span>
                <span className={styles.productName}>
                  {lead.productName ?? `Product ${lead.productId.slice(0, 8)}`}
                </span>
                <span className={styles.leadCardSummary}>
                  {lead.callbackReason ??
                    lead.conversationSummary ??
                    "Conversation captured. No summary is available yet."}
                </span>
                <span className={styles.leadCardFooter}>
                  <StatusPill compact status={lead.callbackStatus} />
                  <span className={styles.metaInline}>
                    {lead.preferredCallbackText ? (
                      <>
                        <ClockIcon />
                        {lead.preferredCallbackText}
                      </>
                    ) : lead.phone ? (
                      <>
                        <PhoneIcon />
                        {lead.phone}
                      </>
                    ) : null}
                  </span>
                </span>
              </span>
              <ChevronIcon className={styles.cardChevron} />
            </button>
          ))
        ) : (
          <div className={styles.emptyState}>
            <span>0</span>
            <h3>No leads match this view</h3>
            <p>
              Try another status or remove part of your search to widen the
              result.
            </p>
          </div>
        )}
      </div>
      <span className={styles.srOnly}>
        Available statuses:{" "}
        {Object.values(statusLabels).join(", ")}
      </span>
    </section>
  );
}
