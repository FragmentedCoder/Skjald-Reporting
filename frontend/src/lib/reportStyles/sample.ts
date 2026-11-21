// The sample report the style editor draws a style on: the incident report Skjald ships
// as its sample template, filled in.

import { customNames, sampleCustom, type CustomField } from "#lib/customFields.js";
import { libraryNames, libraryValues, type LibraryEntry } from "#lib/library.js";
import { sampleTemplate } from "#lib/shared.js";
import { sampleContext, type PreviewInput } from "#lib/templates/preview.js";
import type { TemplateContent } from "#lib/templates/types.js";
import { pageTexts } from "./look";
import type { ResolvedStyle } from "./resolve";

/**
 * What the sample report is worked out from. A page design's text reads the report's
 * context, custom fields and the shared library (vars.<key>, text.<key>), which is what
 * the server checks it against when the style is saved: the library's entries come
 * along, or text that reads one would draw as a warning sign here and print fine.
 */
export function sampleReport(style: ResolvedStyle, library: LibraryEntry[], fields: CustomField[], timezone?: string): PreviewInput {
  const sample = sampleTemplate as unknown as TemplateContent;
  return {
    content: sample,
    answers: sample.sample.answers,
    assets: {},
    timezone,
    context: sampleContext({ customer: sampleCustom(fields, "customer"), project: sampleCustom(fields, "project") }),
    library: { names: { ...libraryNames(library), ...customNames(fields) }, ...libraryValues(library) },
    pageTexts: pageTexts(style),
  };
}
