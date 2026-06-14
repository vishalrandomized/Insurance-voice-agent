"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { CallbackStatus } from "@insurance/contracts";
import {
  demoLeads,
  getLead,
  getLeads,
  type LeadWithActivity,
  updateCallbackStatus,
} from "./api";

const POLL_INTERVAL_MS = 8_000;

export function useLeads() {
  const [leads, setLeads] = useState<LeadWithActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [isDemoData, setIsDemoData] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      const next = await getLeads();
      if (!mounted.current) return;
      setLeads(next);
      setError(null);
      setIsDemoData(false);
    } catch (cause) {
      if (!mounted.current) return;
      setError(cause instanceof Error ? cause.message : "Unable to load leads");
      setLeads((current) => (current.length ? current : demoLeads));
      setIsDemoData(true);
    } finally {
      if (mounted.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh(true);
    }, POLL_INTERVAL_MS);

    const onVisible = () => {
      if (document.visibilityState === "visible") void refresh(true);
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      mounted.current = false;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  const loadDetail = useCallback(
    async (leadId: string): Promise<LeadWithActivity> => {
      if (isDemoData) {
        return leads.find((lead) => lead.id === leadId) ?? demoLeads[0];
      }
      const detail = await getLead(leadId);
      setLeads((current) =>
        current.map((lead) =>
          lead.id === leadId ? { ...lead, ...detail } : lead,
        ),
      );
      return detail;
    },
    [isDemoData, leads],
  );

  const setCallbackStatus = useCallback(
    async (leadId: string, status: CallbackStatus) => {
      const before = leads.find((lead) => lead.id === leadId);
      if (!before) throw new Error("Lead not found");

      const optimistic: LeadWithActivity = {
        ...before,
        callbackStatus: status,
        updatedAt: new Date().toISOString(),
      };
      setLeads((current) =>
        current.map((lead) => (lead.id === leadId ? optimistic : lead)),
      );

      try {
        if (isDemoData) {
          await new Promise((resolve) => window.setTimeout(resolve, 350));
          return optimistic;
        }
        const saved = await updateCallbackStatus(leadId, status, before);
        setLeads((current) =>
          current.map((lead) =>
            lead.id === leadId ? { ...lead, ...saved } : lead,
          ),
        );
        return saved;
      } catch (cause) {
        setLeads((current) =>
          current.map((lead) => (lead.id === leadId ? before : lead)),
        );
        throw cause;
      }
    },
    [isDemoData, leads],
  );

  return {
    leads,
    loading,
    refreshing,
    isDemoData,
    error,
    refresh,
    loadDetail,
    setCallbackStatus,
  };
}
