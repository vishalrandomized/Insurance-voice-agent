"use client";

import { useEffect, useMemo, useState } from "react";
import type { CallbackStatus } from "@insurance/contracts";
import {
  filterLeads,
  type LeadWithActivity,
} from "../../lib/leads/api";
import { useLeads } from "../../lib/leads/use-leads";
import { LeadDetail } from "./lead-detail";
import { LeadList } from "./lead-list";
import { RefreshIcon } from "./icons";
import styles from "./sales-dashboard.module.css";

export function SalesDashboard() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<CallbackStatus | "all">("all");
  const [selected, setSelected] = useState<LeadWithActivity | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [documentStatus, setDocumentStatus] = useState(
    "Upload the insurance PDF that the customer advisor will pitch and answer from.",
  );
  const [uploading, setUploading] = useState(false);
  const {
    leads,
    loading,
    refreshing,
    isDemoData,
    error,
    refresh,
    loadDetail,
    setCallbackStatus,
  } = useLeads();

  useEffect(() => {
    if (!selected) return;
    const current = leads.find((lead) => lead.id === selected.id);
    if (current) setSelected((detail) => ({ ...detail, ...current }));
  }, [leads, selected?.id]);

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        document.querySelector<HTMLInputElement>('input[type="search"]')?.focus();
      }
      if (event.key === "Escape") setSelected(null);
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  const visibleLeads = useMemo(
    () => filterLeads(leads, { status, query }),
    [leads, query, status],
  );

  const requestedCount = leads.filter(
    (lead) => lead.callbackStatus === "requested",
  ).length;
  const activeCount = leads.filter(
    (lead) => lead.callbackStatus === "in_progress",
  ).length;
  const completedCount = leads.filter(
    (lead) => lead.callbackStatus === "completed",
  ).length;

  async function selectLead(lead: LeadWithActivity) {
    setSelected(lead);
    setDetailLoading(true);
    setSaveError(null);
    try {
      setSelected(await loadDetail(lead.id));
    } catch {
      setSelected(lead);
    } finally {
      setDetailLoading(false);
    }
  }

  async function changeStatus(nextStatus: CallbackStatus) {
    if (!selected || selected.callbackStatus === nextStatus) return;
    const before = selected;
    setSaveError(null);
    setSaving(true);
    setSelected({
      ...selected,
      callbackStatus: nextStatus,
      updatedAt: new Date().toISOString(),
    });
    try {
      setSelected(await setCallbackStatus(selected.id, nextStatus));
    } catch (cause) {
      setSelected(before);
      setSaveError(
        cause instanceof Error ? cause.message : "The update did not save.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function uploadDocument(file: File) {
    setUploading(true);
    setDocumentStatus("Indexing policy pages and citations...");
    const body = new FormData();
    body.append("file", file);
    try {
      const apiUrl = (
        process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
      ).replace(/\/$/, "");
      const response = await fetch(`${apiUrl}/api/documents`, {
        method: "POST",
        body,
      });
      if (!response.ok) throw new Error(await response.text());
      const result = (await response.json()) as {
        filename: string;
        pageCount: number;
      };
      setDocumentStatus(
        `${result.filename} is active · ${result.pageCount} pages indexed`,
      );
    } catch {
      setDocumentStatus("Upload failed. Check the PDF and backend connection.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <main className={styles.dashboard}>
      <header className={styles.topbar}>
        <div className={styles.logoLockup}>
          <span className={styles.logoMark}>AP</span>
          <span>AssureLine</span>
          <small>Advisor console</small>
        </div>
        <div className={styles.liveIndicator}>
          <span />
          {isDemoData ? "Demo workspace" : "Live lead feed"}
        </div>
        <div className={styles.topbarActions}>
          <button
            className={styles.refreshButton}
            disabled={refreshing}
            onClick={() => void refresh()}
            type="button"
          >
            <RefreshIcon className={refreshing ? styles.spinning : ""} />
            Refresh
          </button>
          <div className={styles.advisorIdentity}>
            <span>VT</span>
            <div>
              <strong>Vishal</strong>
              <small>Sales advisor</small>
            </div>
          </div>
        </div>
      </header>

      <section className={styles.workspaceHeader}>
        <div>
          <p className={styles.eyebrow}>Policy sales desk</p>
          <h1>Customer follow-up queue</h1>
          <p>
            Upload the policy PDF once, then review customer conversations and
            callback requests collected by the advisor.
          </p>
        </div>
        <div className={styles.metrics}>
          <article className={styles.metricUrgent}>
            <span>Needs action</span>
            <strong>{String(requestedCount).padStart(2, "0")}</strong>
            <small>Customer requested</small>
          </article>
          <article>
            <span>In progress</span>
            <strong>{String(activeCount).padStart(2, "0")}</strong>
            <small>Advisor assigned</small>
          </article>
          <article>
            <span>Completed</span>
            <strong>{String(completedCount).padStart(2, "0")}</strong>
            <small>Closed conversations</small>
          </article>
        </div>
      </section>

      <section className={styles.documentBar}>
        <div>
          <strong>Active product knowledge</strong>
          <span>{documentStatus}</span>
        </div>
        <label className={styles.uploadButton}>
          {uploading ? "Indexing..." : "Upload policy PDF"}
          <input
            accept="application/pdf"
            disabled={uploading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void uploadDocument(file);
              event.target.value = "";
            }}
            type="file"
          />
        </label>
      </section>

      {error && isDemoData ? (
        <div className={styles.demoBanner}>
          The backend is unavailable, so representative demo leads are shown.
          Status interactions remain enabled for preview.
        </div>
      ) : null}

      <section
        className={`${styles.contentGrid} ${
          selected ? styles.contentGridWithDetail : ""
        }`}
      >
        {loading ? (
          <div className={styles.listSkeleton}>
            <div />
            <div />
            <div />
          </div>
        ) : (
          <LeadList
            leads={visibleLeads}
            onQueryChange={setQuery}
            onSelect={(lead) => void selectLead(lead)}
            onStatusChange={setStatus}
            query={query}
            selectedId={selected?.id ?? null}
            status={status}
          />
        )}
        <LeadDetail
          lead={selected}
          loading={detailLoading}
          onClose={() => setSelected(null)}
          onStatusChange={(nextStatus) => void changeStatus(nextStatus)}
          saveError={saveError}
          saving={saving}
        />
      </section>
    </main>
  );
}
