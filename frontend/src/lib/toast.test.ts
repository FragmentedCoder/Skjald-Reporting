import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  announcement,
  clearToasts,
  dismiss,
  hold,
  LIFETIME_MS,
  MAX_VISIBLE,
  release,
  toast,
  toasts,
} from "./toast.svelte";

const texts = () => toasts.map((t) => t.text);

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  clearToasts();
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

  it("can stay longer when they need to", () => {
    toast("Signed out in two minutes.", "warning", { lifetime: 120_000 });
    vi.advanceTimersByTime(119_999);
    expect(toasts).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(toasts).toHaveLength(0);
  });

  it("can be closed sooner", () => {
    const id = toast("Saved.", "ok");
    dismiss(id);
    expect(toasts).toHaveLength(0);
  });

  it("with the same key are updated in place, not added again", () => {
    const first = toast("Signed out.", "warning", { key: "session" });
    vi.advanceTimersByTime(20_000);
    const second = toast("Signed out, again.", "warning", { key: "session" });
    expect(second).toBe(first);
    expect(texts()).toEqual(["Signed out, again."]);
    // ...and their 30 seconds start over.
    vi.advanceTimersByTime(20_000);
    expect(toasts).toHaveLength(1);
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

  it("are read out to screen readers", () => {
    toast("Saved.", "ok");
    toast("Couldn't save.", "critical");
    vi.advanceTimersByTime(100);
    expect(announcement).toEqual({ polite: "Saved.", assertive: "Couldn't save." });
  });
});

describe("the queue", () => {
  it("shows at most three; the next waits and gets its full time once shown", () => {
    for (const text of ["one", "two", "three", "four"]) toast(text);
    expect(MAX_VISIBLE).toBe(3);
    expect(texts()).toEqual(["one", "two", "three"]);

    vi.advanceTimersByTime(10_000);
    dismiss(toasts[0].id);
    expect(texts()).toEqual(["two", "three", "four"]);

    vi.advanceTimersByTime(20_000); // two and three are done; four has 10 seconds left
    expect(texts()).toEqual(["four"]);
    vi.advanceTimersByTime(10_000);
    expect(toasts).toHaveLength(0);
  });

  it("lets urgent ones go first", () => {
    for (const text of ["one", "two", "three", "four"]) toast(text);
    toast("Your account was disabled.", "critical");
    dismiss(toasts[0].id);
    expect(texts()).toEqual(["two", "three", "Your account was disabled."]);
  });

  it("updates a waiting toast in place too", () => {
    for (const text of ["one", "two", "three"]) toast(text);
    toast("Signed out.", "warning", { key: "session" });
    toast("Signed out, again.", "warning", { key: "session" });
    dismiss(toasts[0].id);
    expect(texts()).toEqual(["two", "three", "Signed out, again."]);
  });

  it("is emptied with the rest", () => {
    for (const text of ["one", "two", "three", "four", "five"]) toast(text);
    clearToasts();
    expect(toasts).toHaveLength(0);
    toast("six");
    expect(texts()).toEqual(["six"]);
  });
});
