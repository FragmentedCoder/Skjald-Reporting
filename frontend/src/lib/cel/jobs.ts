// What the expression worker does with each batch it's sent (worker.ts runs it off
// the page's thread; this part is plain so it can be tested without a Worker). The
// engine is made once per set of declared names and kept while they stay the same.

import { preview, type PreviewInput } from "#lib/templates/preview.js";
import { Engine, ExpressionError, type EngineOptions, type Kind } from "./engine";

export interface Setup {
  /** Changes whenever the declarations or options change. */
  key: string;
  declarations: Record<string, string>;
  options: EngineOptions;
}

export type Job =
  | { kind: "check"; expr: string }
  | { kind: "evaluate"; expr: string }
  | { kind: "references"; expr: string }
  /** Everything a template prints for some answers (templates/preview.ts). */
  | { kind: "preview"; input: PreviewInput };

export type Result = { ok: true; value: unknown } | { ok: false; kind: Kind; message: string };

export interface Request {
  id: number;
  /** Sent with the first batch, and again whenever it changes. */
  setup?: Setup;
  /** The values every evaluate job in the batch reads. */
  values: Record<string, unknown>;
  jobs: Job[];
}

export interface Response {
  id: number;
  results: Result[];
}

export class JobRunner {
  #engine: Engine | null = null;
  #key = "";

  handle(request: Request): Response {
    if (request.setup && request.setup.key !== this.#key) {
      this.#engine = new Engine(request.setup.declarations, request.setup.options);
      this.#key = request.setup.key;
    }
    const engine = this.#engine;
    const results = request.jobs.map((job): Result => {
      if (job.kind === "preview") {
        try {
          return { ok: true, value: preview(job.input) };
        } catch (error) {
          return { ok: false, kind: "runtime", message: error instanceof Error ? error.message : String(error) };
        }
      }
      if (!engine) return { ok: false, kind: "runtime", message: "The expression worker has no names to work with yet." };
      try {
        if (job.kind === "check") return { ok: true, value: engine.check(job.expr) };
        if (job.kind === "references") return { ok: true, value: engine.references(job.expr) };
        return { ok: true, value: engine.evaluate(job.expr, request.values) };
      } catch (error) {
        if (error instanceof ExpressionError) return { ok: false, kind: error.kind, message: error.message };
        return { ok: false, kind: "runtime", message: error instanceof Error ? error.message : String(error) };
      }
    });
    return { id: request.id, results };
  }
}
