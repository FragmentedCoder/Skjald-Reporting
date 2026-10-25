import { describe, expect, it, vi } from "vitest";
import { dateRange } from "./format";

describe("dateRange", () => {
  it("shows both dates, or says which one it has", () => {
    expect(dateRange("2026-10-01", "2026-11-03")).toBe("1 Oct 2026 – 3 Nov 2026");
    expect(dateRange("2026-10-01", null)).toBe("From 1 Oct 2026");
    expect(dateRange(null, "2026-11-03")).toBe("Until 3 Nov 2026");
    expect(dateRange(null, undefined)).toBe("—");
  });
});

describe("date", () => {
  it("keeps a plain date on its day, west of UTC too", async () => {
    vi.stubEnv("TZ", "America/Los_Angeles");
    try {
      vi.resetModules();
      const fresh = await import("./format");
      expect(fresh.date("2026-10-01")).toBe("1 Oct 2026");
    } finally {
      vi.unstubAllEnvs();
      vi.resetModules();
    }
  });
});
