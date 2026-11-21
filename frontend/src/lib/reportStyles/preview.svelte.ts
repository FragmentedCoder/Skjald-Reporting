// The style the builder shows a template in: the company's default style to start with,
// or another of its styles, a customer's style (of customers this person sees), or the
// Skjald default.

import { branding } from "#lib/branding.svelte.js";
import { stylesApi, type Style, type StyleSummary } from "./api";
import { lookOf, pageTexts, type PageLook } from "./look";
import { resolve, type ResolvedStyle } from "./resolve";

/**
 * Where a style's picture loads from: its own, or the company style it stacks on. In
 * the style editor that's the one chosen under "Stacks on" (`base`), which isn't the
 * one the style was saved with until it's saved again.
 */
export function imageOf(style: Style | null, base: number | null | undefined = style?.based_on): (sha: string) => string | null {
  return (sha) => {
    if (!style) return null;
    if (style.assets.some((a) => a.sha256 === sha)) return stylesApi.assetUrl(style.id, sha);
    return base ? stylesApi.assetUrl(base, sha) : null;
  };
}

export class PreviewStyle {
  choices = $state<StyleSummary[]>([]);
  /** The chosen style's ID; null: the Skjald default. */
  chosen = $state<number | null>(null);
  style = $state<Style | null>(null);
  problem = $state<string | null>(null);
  resolved: ResolvedStyle = $derived(resolve(this.style ? [...this.style.below, this.style.content] : []));
  /** The text elements' words, for the preview to fill in. */
  texts: Record<string, string> = $derived(pageTexts(this.resolved));

  async load(): Promise<void> {
    try {
      this.choices = await stylesApi.list();
      await this.choose(this.choices.find((s) => s.is_default && s.customer_id === null)?.id ?? null);
    } catch {
      this.problem = "Skjald couldn't load the styles, so the preview uses the Skjald default.";
    }
  }

  async choose(id: number | null): Promise<void> {
    this.chosen = id;
    this.style = id === null ? null : await stylesApi.get(id);
  }

  /** The pages' look; a template can leave "Made with Skjald" off its own reports. */
  look(filled: Record<string, string> | undefined, madeWith = true): PageLook {
    return lookOf(this.resolved, {
      image: imageOf(this.style),
      logos: { company: branding.current.logo_url, customer: null },
      madeWith: branding.current.made_with_skjald && madeWith,
      texts: filled,
    });
  }
}
