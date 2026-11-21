// The preview kept up to date as a template or its sample answers change: worked out in
// the expression worker a moment after the last change, and split into pages here.

import { CelClient, TOO_LONG } from "#lib/cel/client.js";
import { paginate, type Paged } from "./pages";
import type { PreviewInput, PreviewModel } from "./preview";

const AFTER_MS = 250;
// A whole preview is thousands of expressions for a large template, or a small one
// printed for hundreds of rows, so it gets longer than the second one expression gets.
// It runs off the page's thread either way: the builder stays quick meanwhile.
const TIME_LIMIT_MS = 10_000;
const SETUP = { key: "preview", declarations: {}, options: {} };

export class LivePreview {
  model = $state<PreviewModel | null>(null);
  paged = $state<Paged | null>(null);
  problem = $state<string | null>(null);
  #client = new CelClient();
  #timer: ReturnType<typeof setTimeout> | undefined;
  #asked = 0;

  /** Works the preview out again soon, from this input (a snapshot, not live state). */
  update(input: PreviewInput): void {
    clearTimeout(this.#timer);
    this.#timer = setTimeout(() => void this.#run(input), AFTER_MS);
  }

  async #run(input: PreviewInput): Promise<void> {
    const asked = ++this.#asked;
    const [result] = await this.#client.run(SETUP, {}, [{ kind: "preview", input }], TIME_LIMIT_MS);
    if (asked !== this.#asked) return;
    if (result.ok) {
      this.model = result.value as PreviewModel;
      this.paged = paginate(this.model.blocks);
      this.problem = null;
    } else {
      this.problem = result.message === TOO_LONG ? "Working out the preview took too long, so Skjald stopped it. Check the rules for repeating groups." : result.message;
    }
  }

  close(): void {
    clearTimeout(this.#timer);
    this.#client.close();
  }
}
