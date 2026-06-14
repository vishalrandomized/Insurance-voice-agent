import { describe, expect, it } from "vitest";
import type { LeadWithActivity } from "./api";
import { filterLeads } from "./api";

const baseLead: LeadWithActivity = {
  id: "lead-1",
  sessionId: "session-1",
  customerName: "Aanya Mehta",
  phone: null,
  productId: "product-1",
  callbackStatus: "requested",
  callbackReason: "Family coverage",
  preferredCallbackText: null,
  preferredCallbackAt: null,
  conversationSummary: "Asked about waiting periods.",
  createdAt: "2026-06-12T10:00:00Z",
  updatedAt: "2026-06-12T10:00:00Z",
};

describe("filterLeads", () => {
  it("puts callback-ready leads before completed leads", () => {
    const completed = {
      ...baseLead,
      id: "lead-2",
      callbackStatus: "completed" as const,
    };

    expect(
      filterLeads([completed, baseLead], { status: "all", query: "" }).map(
        (lead) => lead.id,
      ),
    ).toEqual(["lead-1", "lead-2"]);
  });

  it("filters by customer intent text", () => {
    expect(
      filterLeads([baseLead], { status: "all", query: "waiting" }),
    ).toHaveLength(1);
    expect(
      filterLeads([baseLead], { status: "all", query: "motor insurance" }),
    ).toHaveLength(0);
  });
});
