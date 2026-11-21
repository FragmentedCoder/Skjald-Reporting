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
  it("fails a batch that can't be sent, and carries on", async () => {
    let calls = 0;
    const client = new CelClient(() => {
      const worker = new FakeWorker();
      const post = worker.postMessage.bind(worker);
      worker.postMessage = (request) => {
        if (calls++ === 0) throw new DOMException("could not be cloned", "DataCloneError");
        post(request);
      };
      return worker;
    });
    const [failed] = await client.run(SETUP, {}, [{ kind: "check", expr: "answers.cvss" }]);
    expect(failed).toMatchObject({ ok: false, kind: "runtime" });
    expect(await client.run(SETUP, {}, [{ kind: "check", expr: "answers.cvss" }])).toEqual([{ ok: true, value: "double" }]);
  });

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

  it("reads an answer that was waiting when the time ran out, and gives a batch its own limit", async () => {
    // An answer a little late stands for one that came in time but waited behind the
    // page's own work: it's read, not thrown away with the worker.
    const late = (ms: number) => () => {
      const worker = new FakeWorker(() => true);
      worker.postMessage = (request) => {
        setTimeout(() => worker.onmessage?.({ data: new JobRunner().handle(request) } as MessageEvent<Response>), ms);
      };
      return worker;
    };
    const jobs = [{ kind: "check" as const, expr: "answers.cvss" }];
    expect(await new CelClient(late(30), 20).run(SETUP, {}, jobs)).toEqual([{ ok: true, value: "double" }]);
    expect(await new CelClient(late(150), 20).run(SETUP, {}, jobs)).toEqual([{ ok: false, kind: "runtime", message: TOO_LONG }]);
    expect(await new CelClient(late(150), 20).run(SETUP, {}, jobs, 500)).toEqual([{ ok: true, value: "double" }]);
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
