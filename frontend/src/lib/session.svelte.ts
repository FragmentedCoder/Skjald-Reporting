import { goto } from "$app/navigation";
import { resolve } from "$app/paths";
import { api, ApiError, setCsrfToken } from "./api";

export type Method = "totp" | "webauthn" | "recovery_code";
export type Role = "administrator" | "report_designer" | "technician" | "reviewer" | "auditor";

export interface SessionInfo {
  user: { id: number; username: string; display_name: string; roles: Role[] };
  second_factor: "enrol" | "verify" | "done";
  methods: Method[];
  csrf_token: string;
  expires_at: string;
}

export interface SecondFactorResult {
  session: SessionInfo;
  recovery_codes: string[] | null;
}

export const session = $state<{
  current: SessionInfo | null;
  loaded: boolean;
  // A message for the sign-in page, such as why the session ended.
  notice: string | null;
  // A fresh install: every page leads to the setup wizard until it is finished.
  setupNeeded: boolean;
}>({ current: null, loaded: false, notice: null, setupNeeded: false });

export function useSession(info: SessionInfo | null): void {
  session.current = info;
  setCsrfToken(info?.csrf_token ?? null);
}

export async function loadSession(): Promise<SessionInfo | null> {
  try {
    session.setupNeeded = (await api<{ needed: boolean }>("GET", "/setup/status")).needed;
    useSession(await api<SessionInfo>("GET", "/auth/session"));
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) throw error;
    useSession(null);
  } finally {
    session.loaded = true;
  }
  return session.current;
}

export type Place = "/" | "/setup" | "/sign-in" | "/sign-in/set-up" | "/sign-in/verify";

/** The page a session belongs on: setup, sign in, set up a second factor, use it, or the app. */
export function placeFor(info: SessionInfo | null, setupNeeded = session.setupNeeded): Place {
  if (setupNeeded) return "/setup";
  if (!info) return "/sign-in";
  if (info.second_factor === "enrol") return "/sign-in/set-up";
  if (info.second_factor === "verify") return "/sign-in/verify";
  return "/";
}

/**
 * Load the session if needed, and move on if this page isn't where it belongs.
 * Returns the session when the page may show (null when it moved on, or when the
 * page is for people who aren't signed in).
 */
export async function settle(here: Place): Promise<SessionInfo | null> {
  const info = session.loaded ? session.current : await loadSession();
  const place = placeFor(info);
  if (place !== here) await goto(resolve(place), { replaceState: true });
  return place === here ? info : null;
}

/** The server ended the session (signed out elsewhere, timed out, locked). */
export async function sessionEnded(message: string): Promise<void> {
  useSession(null);
  session.notice = message;
  await goto(resolve(placeFor(null)), { replaceState: true });
}

export async function signOut(): Promise<void> {
  try {
    await api("POST", "/auth/sign-out");
  } catch {
    // Signed out on the server already, or unreachable: forget the session either way.
  }
  useSession(null);
  await goto(resolve(placeFor(null)), { replaceState: true });
}
