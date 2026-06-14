import { describe, expect, it } from "vitest";

import { isValidDemoPassword } from "./auth";

describe("isValidDemoPassword", () => {
  it("accepts the configured password", () => {
    expect(isValidDemoPassword("demo-sales", "demo-sales")).toBe(true);
  });

  it("accepts trimmed and case-insensitive input", () => {
    expect(isValidDemoPassword("  DEMO-SALES  ", "demo-sales")).toBe(true);
  });

  it("accepts the legacy reversed demo password alias", () => {
    expect(isValidDemoPassword("sales-demo", "demo-sales")).toBe(true);
  });

  it("rejects unrelated passwords", () => {
    expect(isValidDemoPassword("wrong-password", "demo-sales")).toBe(false);
  });
});
