// Toasts: short messages in the corner that never move the page. They stay 30
// seconds (paused while the pointer or focus is on them, so nobody is rushed),
// and the × closes them sooner.

export type ToastTone = "ok" | "info" | "warning" | "critical";

export interface ToastAction {
  label: string;
  run: () => void;
}

export interface Toast {
  id: number;
  tone: ToastTone;
  text: string;
  action?: ToastAction;
  // Showing a toast with a key that's already up replaces it instead of stacking.
  key?: string;
}

export const LIFETIME_MS = 30_000;

export const toasts = $state<Toast[]>([]);

// Bookkeeping only, never shown: deliberately not reactive.
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const timers = new Map<number, { handle?: ReturnType<typeof setTimeout>; left: number; since: number }>();
let nextId = 1;

function start(id: number): void {
  const timer = timers.get(id);
  if (!timer) return;
  timer.since = Date.now();
  timer.handle = setTimeout(() => dismiss(id), timer.left);
}

export function toast(
  text: string,
  tone: ToastTone = "info",
  options: { action?: ToastAction; key?: string } = {},
): number {
  if (options.key) {
    const existing = toasts.find((t) => t.key === options.key);
    if (existing) dismiss(existing.id);
  }
  const id = nextId++;
  toasts.push({ id, tone, text, ...options });
  timers.set(id, { left: LIFETIME_MS, since: Date.now() });
  start(id);
  return id;
}

export function dismiss(id: number): void {
  const timer = timers.get(id);
  if (timer?.handle) clearTimeout(timer.handle);
  timers.delete(id);
  const index = toasts.findIndex((t) => t.id === id);
  if (index >= 0) toasts.splice(index, 1);
}

export function dismissKey(key: string): void {
  const existing = toasts.find((t) => t.key === key);
  if (existing) dismiss(existing.id);
}

/** Stop the clock while someone is reading or using the toast. */
export function hold(id: number): void {
  const timer = timers.get(id);
  if (!timer?.handle) return;
  clearTimeout(timer.handle);
  timer.handle = undefined;
  timer.left = Math.max(timer.left - (Date.now() - timer.since), 1000);
}

export function release(id: number): void {
  const timer = timers.get(id);
  if (timer && !timer.handle) start(id);
}
