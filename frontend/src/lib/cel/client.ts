// Runs batches of template expressions in the expression worker (worker.ts), one
// batch at a time. A batch that runs over the time limit stops the worker; its jobs
// fail with a message and the next batch gets a fresh worker. RE2 already keeps
// regular expressions linear, so this is the second guard the architecture asks for.

import type { Job, Request, Response, Result, Setup } from "./jobs";

export const TIME_LIMIT_MS = 1000;
export const TOO_LONG = "Working this out took too long, so Skjald stopped it.";

/** The part of a Worker the client uses, so tests can stand in for one. */
export interface WorkerLike {
  postMessage(message: Request): void;
  terminate(): void;
  onmessage: ((event: MessageEvent<Response>) => void) | null;
}

const browserWorker = (): WorkerLike =>
  new Worker(new URL("./worker.ts", import.meta.url), { type: "module" }) as unknown as WorkerLike;

interface Pending {
  setup: Setup;
  values: Record<string, unknown>;
  jobs: Job[];
  done: (results: Result[]) => void;
}

export class CelClient {
  #worker: WorkerLike | null = null;
  #sentKey: string | null = null;
  #queue: Pending[] = [];
  #busy = false;
  #nextId = 1;

  constructor(
    private readonly makeWorker: () => WorkerLike = browserWorker,
    private readonly timeLimitMs = TIME_LIMIT_MS,
  ) {}

  run(setup: Setup, values: Record<string, unknown>, jobs: Job[]): Promise<Result[]> {
    return new Promise((done) => {
      this.#queue.push({ setup, values, jobs, done });
      this.#next();
    });
  }

  /** Stops the worker; the next batch starts a new one. */
  close(): void {
    this.#worker?.terminate();
    this.#worker = null;
    this.#sentKey = null;
  }

  #next(): void {
    if (this.#busy) return;
    const pending = this.#queue.shift();
    if (!pending) return;
    this.#busy = true;
    const worker = (this.#worker ??= this.makeWorker());
    const id = this.#nextId++;
    let settled = false;
    const finish = (results: Result[]) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      this.#busy = false;
      pending.done(results);
      this.#next();
    };
    const timer = setTimeout(() => {
      this.close();
      finish(pending.jobs.map(() => ({ ok: false, kind: "runtime", message: TOO_LONG })));
    }, this.timeLimitMs);
    worker.onmessage = (event) => {
      if (event.data.id === id) finish(event.data.results);
    };
    const setup = pending.setup.key === this.#sentKey ? undefined : pending.setup;
    this.#sentKey = pending.setup.key;
    try {
      worker.postMessage({ id, setup, values: pending.values, jobs: pending.jobs });
    } catch (error) {
      // What can't be sent (live state rather than plain data, say) fails its jobs
      // rather than leaving the queue waiting.
      this.#sentKey = null;
      const message = error instanceof Error ? error.message : String(error);
      finish(pending.jobs.map(() => ({ ok: false, kind: "runtime", message })));
    }
  }
}
