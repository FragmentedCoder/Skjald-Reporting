// Toasts: short messages in the corner that never move the page. At most three
// show at once, newest on top; more wait their turn. Each stays 30 seconds
// (paused while the pointer or focus is on it, so nobody is rushed), and the ×
// closes it sooner.

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
  // A toast with a key that's already up is updated in place, not added again.
  key?: string;
  // Milliseconds to stay, when not the usual 30 seconds.
  lifetime?: number;
}

export const LIFETIME_MS = 30_000;
export const MAX_VISIBLE = 3;

/** The toasts on screen, oldest first. */
export const toasts = $state<Toast[]>([]);
/** The latest text for screen readers, by how urgently it's read out. */
export const announcement = $state({ polite: "", assertive: "" });

// Waiting their turn (urgent ones first), and bookkeeping for the timers: never
// shown, so deliberately not reactive.
const waiting: Toast[] = [];
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const timers = new Map<number, { handle?: ReturnType<typeof setTimeout>; left: number; since: number }>();
let nextId = 1;

function start(id: number): void {
  const timer = timers.get(id);
  if (!timer) return;
  timer.since = Date.now();
  timer.handle = setTimeout(() => dismiss(id), timer.left);
}

function restart(item: Toast): void {
  const timer = timers.get(item.id);
  if (!timer) return;
  const held = timer.handle === undefined;
  clearTimeout(timer.handle);
  timer.handle = undefined;
  timer.left = item.lifetime ?? LIFETIME_MS;
  if (!held) start(item.id);
}

// Emptied first, so the same words are read out again.
function announce(item: Toast): void {
  const urgency = item.tone === "critical" ? "assertive" : "polite";
  announcement[urgency] = "";
  setTimeout(() => (announcement[urgency] = item.text), 100);
}

function show(item: Toast): void {
  toasts.push(item);
  timers.set(item.id, { left: item.lifetime ?? LIFETIME_MS, since: Date.now() });
  start(item.id);
  announce(item);
}

export function toast(
  text: string,
  tone: ToastTone = "info",
  options: { action?: ToastAction; key?: string; lifetime?: number } = {},
): number {
  if (options.key) {
    const shown = toasts.find((t) => t.key === options.key);
    const queued = waiting.find((t) => t.key === options.key);
    const existing = shown ?? queued;
    if (existing) {
      Object.assign(existing, { tone, text, action: options.action, lifetime: options.lifetime });
      if (shown) {
        restart(shown);
        announce(shown);
      }
      return existing.id;
    }
  }
  const item: Toast = { id: nextId++, tone, text, ...options };
  if (toasts.length < MAX_VISIBLE) show(item);
  else if (tone === "critical") waiting.unshift(item);
  else waiting.push(item);
  return item.id;
}

export function dismiss(id: number): void {
  const timer = timers.get(id);
  if (timer?.handle) clearTimeout(timer.handle);
  timers.delete(id);
  const index = toasts.findIndex((t) => t.id === id);
  if (index >= 0) {
    // Nothing stale is left for a screen reader to come across later.
    const { text } = toasts[index];
    for (const urgency of ["polite", "assertive"] as const) {
      if (announcement[urgency] === text) announcement[urgency] = "";
    }
    toasts.splice(index, 1);
  }
  const queued = waiting.findIndex((t) => t.id === id);
  if (queued >= 0) waiting.splice(queued, 1);
  while (toasts.length < MAX_VISIBLE && waiting.length) show(waiting.shift()!);
}

export function dismissKey(key: string): void {
  const existing = toasts.find((t) => t.key === key) ?? waiting.find((t) => t.key === key);
  if (existing) dismiss(existing.id);
}

/** Clear every toast, waiting ones too: what they were about no longer applies. */
export function clearToasts(): void {
  waiting.length = 0;
  for (const item of [...toasts]) dismiss(item.id);
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
