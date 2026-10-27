// The template open in the builder: its draft, saved a moment after each change, and
// its problems, checked as the designer types. A template whose newest version is
// published and has no draft shows that version until someone edits it, which starts
// a new draft from it. A save over someone else's newer one is refused by the server;
// the designer then reloads theirs or keeps their own.

import { getContext, setContext } from "svelte";
import { ApiError } from "#lib/api.js";
import { templatesApi, type TemplateDetail } from "./api";
import { check } from "./checks";
import type { Problem, TemplateContent } from "./types";

export type SaveState = "saved" | "unsaved" | "saving" | "conflict" | "failed";

export interface Selection {
  kind: "step" | "question" | "block";
  id: string;
}

export const SAVE_AFTER_MS = 1200;
const CHECK_AFTER_MS = 250;

export class Draft {
  template = $state<TemplateDetail | null>(null);
  content = $state<TemplateContent | null>(null);
  /** Showing a published version, with no draft yet. */
  readonly = $state(false);
  shownVersion = $state<number | null>(null);
  saveState = $state<SaveState>("saved");
  saveMessage = $state<string | null>(null);
  savedAt = $state<string | null>(null);
  problems = $state<Problem[]>([]);
  selection = $state<Selection | null>(null);
  loadError = $state<string | null>(null);

  revision = 0;
  #saved = "";
  #seen = "";
  #saveTimer: ReturnType<typeof setTimeout> | undefined;
  #checkTimer: ReturnType<typeof setTimeout> | undefined;
  #saving: Promise<void> | null = null;

  get id(): number {
    return this.template?.id ?? 0;
  }

  get assets(): string[] {
    return this.template?.assets.map((a) => a.sha256) ?? [];
  }

  async load(id: number): Promise<void> {
    clearTimeout(this.#saveTimer);
    try {
      this.template = await templatesApi.get(id);
      if (this.template.draft) {
        const draft = await templatesApi.draft(id);
        this.#use(draft.content, draft.revision, false, null);
        this.savedAt = draft.saved_at;
      } else {
        const newest = this.template.versions[0];
        const version = await templatesApi.version(id, newest.number);
        this.#use(version.content, 0, true, newest.number);
      }
      this.loadError = null;
    } catch (error) {
      this.loadError = error instanceof ApiError ? error.message : "The template couldn't be loaded.";
      throw error;
    }
  }

  #use(content: TemplateContent, revision: number, readonly: boolean, version: number | null) {
    this.content = content;
    this.revision = revision;
    this.readonly = readonly;
    this.shownVersion = version;
    this.#saved = this.#seen = JSON.stringify(content);
    this.saveState = "saved";
    this.saveMessage = null;
    this.problems = check(content, { assets: this.assets });
  }

  /** Called with the content's JSON whenever it may have changed. */
  noticed(text: string): void {
    if (text === this.#seen || this.content === null) return;
    this.#seen = text;
    clearTimeout(this.#checkTimer);
    this.#checkTimer = setTimeout(() => {
      if (this.content) this.problems = check($state.snapshot(this.content) as TemplateContent, { assets: this.assets });
    }, CHECK_AFTER_MS);
    if (this.readonly || this.saveState === "conflict") return;
    if (text !== this.#saved) {
      this.saveState = "unsaved";
      clearTimeout(this.#saveTimer);
      this.#saveTimer = setTimeout(() => void this.save(), SAVE_AFTER_MS);
    }
  }

  /** Saves now if anything is unsaved; waits for a save under way. */
  async save(): Promise<void> {
    clearTimeout(this.#saveTimer);
    if (this.#saving) await this.#saving;
    if (this.content === null || this.readonly || this.saveState === "conflict") return;
    const content = $state.snapshot(this.content) as TemplateContent;
    const text = JSON.stringify(content);
    if (text === this.#saved) {
      if (this.saveState !== "failed") this.saveState = "saved";
      return;
    }
    this.saveState = "saving";
    this.#saving = (async () => {
      try {
        const saved = await templatesApi.save(this.id, content, this.revision);
        this.revision = saved.revision;
        this.#saved = text;
        this.savedAt = saved.saved_at;
        this.saveMessage = null;
        this.saveState = JSON.stringify(this.content) === text ? "saved" : "unsaved";
        if (this.saveState === "unsaved") this.#saveTimer = setTimeout(() => void this.save(), SAVE_AFTER_MS);
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          this.saveState = "conflict";
        } else {
          this.saveState = "failed";
        }
        this.saveMessage = error instanceof ApiError ? error.message : "The draft couldn't be saved.";
      }
    })();
    await this.#saving;
    this.#saving = null;
  }

  /** After a conflict: their version, losing the changes here. */
  async reload(): Promise<void> {
    await this.load(this.id);
  }

  /** After a conflict: this version, over theirs. */
  async keepMine(): Promise<void> {
    const theirs = await templatesApi.draft(this.id);
    this.revision = theirs.revision;
    this.saveState = "unsaved";
    await this.save();
  }

  /** Starts a draft from the version shown, so it can be edited. */
  async edit(): Promise<void> {
    if (!this.readonly) return;
    const draft = await templatesApi.startDraft(this.id, this.shownVersion ?? undefined);
    this.template = await templatesApi.get(this.id);
    this.#use(draft.content, draft.revision, false, null);
  }

  async publish(note: string): Promise<number> {
    await this.save();
    if (this.saveState !== "saved") throw new ApiError(0, this.saveMessage ?? "Save the draft first.");
    const version = await templatesApi.publish(this.id, this.revision, note);
    await this.load(this.id);
    return version.number;
  }

  async discard(): Promise<void> {
    clearTimeout(this.#saveTimer);
    await templatesApi.discard(this.id);
    await this.load(this.id);
  }

  problemsFor(element: string, field?: string): Problem[] {
    return this.problems.filter((p) => p.element === element && (field === undefined || p.field === field));
  }

  get unsaved(): boolean {
    return this.saveState === "unsaved" || this.saveState === "saving";
  }
}

const KEY = Symbol("template-draft");

export function shareDraft(draft: Draft): void {
  setContext(KEY, draft);
}

export function useDraft(): Draft {
  return getContext<Draft>(KEY);
}
