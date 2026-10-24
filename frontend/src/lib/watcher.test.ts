import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSession, type SessionInfo } from "./session.svelte";
import { dismiss, toasts } from "./toast.svelte";

const NOW = Date.parse("2026-10-24T12:00:00Z");
const LATER = "2026-10-25T00:00:00Z";

function signedIn(idleExpiresAt: string): SessionInfo {
  return {
    user: {
      id: 1, username: "astrid", display_name: "Astrid Fjeld", theme: "system",
      colours: { primary: null, accent: null }, avatar_url: null, roles: [], capabilities: [],
    },
    second_factor: "done",
    methods: [],
    password_change_required: false,
    recovery_codes_left: null,
    csrf_token: "t",
    idle_expires_at: idleExpiresAt,
    expires_at: LATER,
  };
}

function statusAnswers(idleExpiresAt: () => string) {
  const fetch = vi.fn(async () =>
    new Response(JSON.stringify({ idle_expires_at: idleExpiresAt(), expires_at: LATER }), {
      status: 200,
    }),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

beforeEach(() => {
  vi.useFakeTimers({ now: NOW });
  vi.stubGlobal("window", {}); // the watcher only runs in a browser
});

afterEach(() => {
  useSession(null);
  for (const item of [...toasts]) dismiss(item.id);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("the idle warning", () => {
  it("shows once, and doesn't keep asking the server", async () => {
    const idle = new Date(NOW + 90_000).toISOString(); // already inside the last two minutes
    const fetch = statusAnswers(() => idle);
    useSession(signedIn(idle));

    await vi.advanceTimersByTimeAsync(20_000);

    expect(fetch.mock.calls.length).toBeLessThanOrEqual(2);
    expect(toasts.filter((t) => t.key === "idle")).toHaveLength(1);
  });

  it("waits until two minutes before the sign-out", async () => {
    const idle = new Date(NOW + 30 * 60_000).toISOString();
    statusAnswers(() => idle);
    useSession(signedIn(idle));

    await vi.advanceTimersByTimeAsync(27 * 60_000);
    expect(toasts.filter((t) => t.key === "idle")).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(2 * 60_000);
    expect(toasts.filter((t) => t.key === "idle")).toHaveLength(1);
  });

  it("goes away when you stay signed in, and comes back only before the new deadline", async () => {
    let idle = new Date(NOW + 90_000).toISOString();
    const fetch = vi.fn(async (url: string) => {
      const body = url.endsWith("/status")
        ? { idle_expires_at: idle, expires_at: LATER }
        : signedIn(idle);
      return new Response(JSON.stringify(body), { status: 200 });
    });
    vi.stubGlobal("fetch", fetch);
    useSession(signedIn(idle));
    await vi.advanceTimersByTimeAsync(1_000);
    const warning = toasts.find((t) => t.key === "idle");
    expect(warning?.action?.label).toBe("Stay signed in");

    idle = new Date(Date.now() + 30 * 60_000).toISOString(); // the server counts the click
    warning?.action?.run();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(toasts.filter((t) => t.key === "idle")).toHaveLength(0);

    await vi.advanceTimersByTimeAsync(27 * 60_000);
    expect(toasts.filter((t) => t.key === "idle")).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(2 * 60_000);
    expect(toasts.filter((t) => t.key === "idle")).toHaveLength(1);
  });
});
