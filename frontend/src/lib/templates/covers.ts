// Each template's first page, small, for the Templates page's cards: worked out from
// the template itself (its draft, else its newest version) with its sample answers, the
// way the builder's preview is, one template after another in a single expression
// worker, and only when its card comes into view.

import { branding } from "#lib/branding.svelte.js";
import { CelClient } from "#lib/cel/client.js";
import { customFieldsApi, customNames, sampleCustom, type CustomField } from "#lib/customFields.js";
import { libraryApi, libraryNames, libraryValues, type LibraryEntry } from "#lib/library.js";
import { templatesApi, type TemplateSummary } from "./api";
import { paginate, type Paged } from "./pages";
import { sampleContext, type PreviewInput, type PreviewModel } from "./preview";

const SETUP = { key: "preview", declarations: {}, options: {} };

export class Covers {
  #client = new CelClient();
  #shared: Promise<Pick<PreviewInput, "context" | "library">> | null = null;

  /** What every template's preview reads besides its own: the sample context and the library. */
  #sharedData(): Promise<Pick<PreviewInput, "context" | "library">> {
    this.#shared ??= Promise.all([libraryApi.list().catch((): LibraryEntry[] => []), customFieldsApi.list().catch((): CustomField[] => [])])
      .then(([library, fields]) => ({
        context: sampleContext({ customer: sampleCustom(fields, "customer"), project: sampleCustom(fields, "project") }),
        library: { names: { ...libraryNames(library), ...customNames(fields) }, ...libraryValues(library) },
      }));
    return this.#shared;
  }

  /** The template's first page, or null when it has none (or couldn't be worked out). */
  async firstPage(template: TemplateSummary, pageTexts: Record<string, string>): Promise<Paged | null> {
    try {
      const content = template.draft
        ? (await templatesApi.draft(template.id)).content
        : template.latest_version !== null ? (await templatesApi.version(template.id, template.latest_version)).content : null;
      if (!content) return null;
      const shared = await this.#sharedData();
      const input: PreviewInput = { content, answers: content.sample.answers, assets: {}, timezone: branding.current.time_zone, pageTexts, ...shared };
      const [result] = await this.#client.run(SETUP, {}, [{ kind: "preview", input }]);
      if (!result.ok) return null;
      const paged = paginate((result.value as PreviewModel).blocks);
      return paged.pages.length ? { pages: paged.pages.slice(0, 1), contents: paged.contents } : null;
    } catch {
      return null;
    }
  }

  close(): void {
    this.#client.close();
  }
}
