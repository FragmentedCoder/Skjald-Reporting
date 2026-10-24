import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dismiss, hold, LIFETIME_MS, release, toast, toasts } from "./toast.svelte";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  for (const item of [...toasts]) dismiss(item.id);
  vi.useRealTimers();
});

describe("toasts", () => {
  it("go away by themselves after 30 seconds", () => {
    toast("Saved.", "ok");
    vi.advanceTimersByTime(LIFETIME_MS - 1);
    expect(toasts).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(toasts).toHaveLength(0);
  });

  it("can be closed sooner", () => {
    const id = toast("Saved.", "ok");
    dismiss(id);
    expect(toasts).toHaveLength(0);
  });

  it("replace one with the same key instead of stacking up", () => {
    toast("Signed out.", "warning", { key: "session" });
    toast("Signed out again.", "warning", { key: "session" });
    toast("Something else.");
    expect(toasts.map((t) => t.text)).toEqual(["Signed out again.", "Something else."]);
  });

  it("wait while someone is reading them", () => {
    const id = toast("Read me.");
    vi.advanceTimersByTime(20_000);
    hold(id);
    vi.advanceTimersByTime(60_000);
    expect(toasts).toHaveLength(1);
    release(id);
    vi.advanceTimersByTime(9_999);
    expect(toasts).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(toasts).toHaveLength(0);
  });
});
