import { describe, expect, it } from "vitest";
import { CelClient, TOO_LONG, type WorkerLike } from "./client";
import { JobRunner, type Request, type Response, type Setup } from "./jobs";

const SETUP: Setup = { key: "1", declarations: { "answers.cvss": "double" }, options: {} };

/** A stand-in worker that answers on the next tick, or never when told to hang. */
class FakeWorker implements WorkerLike {
  onmessage: ((event: MessageEvent<Response>) => void) | null = null;
  readonly sent: Request[] = [];
  terminated = false;
  readonly #runner = new JobRunner();

  constructor(private readonly hang = (request: Request) => request.jobs.some((j) => "expr" in j && j.expr === "hang")) {}

  postMessage(request: Request): void {
    this.sent.push(request);
    if (this.hang(request)) return;
    queueMicrotask(() => this.onmessage?.({ data: this.#runner.handle(request) } as MessageEvent<Response>));
  }

  terminate(): void {
    this.terminated = true;
  }
}

describe("the expression client", () => {
  it("runs a batch and sends the names only when they change", async () => {
    const workers: FakeWorker[] = [];
    const client = new CelClient(() => {
      workers.push(new FakeWorker());
      return workers[workers.length - 1];
    });
    const values = { answers: { cvss: 9.8 } };
    expect(await client.run(SETUP, values, [{ kind: "evaluate", expr: "answers.cvss >= 9.0" }, { kind: "check", expr: "answers.cvss" }]))
      .toEqual([{ ok: true, value: true }, { ok: true, value: "double" }]);
    expect(await client.run(SETUP, values, [{ kind: "check", expr: "answers.nope > 1.0" }])).toEqual([
      { ok: false, kind: "invalid", message: "answers.nope isn't a name this template has." },
    ]);
    expect(workers).toHaveLength(1);
    expect(workers[0].sent.map((r) => r.setup?.key ?? null)).toEqual(["1", null]);
  });

  it("stops a batch that takes too long and starts a fresh worker", async () => {
    const workers: FakeWorker[] = [];
    const client = new CelClient(() => {
      workers.push(new FakeWorker());
      return workers[workers.length - 1];
    }, 20);
    const [slow, after] = await Promise.all([
      client.run(SETUP, {}, [{ kind: "evaluate", expr: "hang" }]),
      client.run(SETUP, {}, [{ kind: "evaluate", expr: "answers.cvss + 1.0" }]),
    ]);
    expect(slow).toEqual([{ ok: false, kind: "runtime", message: TOO_LONG }]);
    expect(after).toEqual([{ ok: true, value: 1 }]);
    expect(workers).toHaveLength(2);
    expect(workers[0].terminated).toBe(true);
    // The new worker gets the names again.
    expect(workers[1].sent[0].setup?.key).toBe("1");
  });
});
