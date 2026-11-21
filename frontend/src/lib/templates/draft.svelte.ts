// The template open in the builder: its draft, saved a moment after each change, and
// its problems, checked as the designer types. A template whose newest version is
// published and has no draft shows that version until someone edits it, which starts
// a new draft from it. A save over someone else's newer one is refused by the server;
// the designer then reloads theirs or keeps their own.

import { getContext, setContext } from "svelte";
import { ApiError } from "#lib/api.js";
import { thisMinute } from "#lib/cel/dates.js";
import { customFieldsApi, customLabels, customNames, sampleCustom, type CustomField } from "#lib/customFields.js";
import { libraryApi, libraryLabels, libraryNames, libraryValues, type LibraryEntry } from "#lib/library.js";
import { toast } from "#lib/toast.svelte.js";
import { templatesApi, type TemplateDetail } from "./api";
import { check } from "./checks";
import { sampleContext } from "./preview";
import type { Problem, TemplateContent } from "./types";

export type SaveState = "saved" | "unsaved" | "saving" | "conflict" | "failed";

export interface Selection {
  kind: "step" | "question" | "block";
  id: string;
}

export const SAVE_AFTER_MS = 1200;
const CHECK_AFTER_MS = 250;
/** Changes closer together than this are one step to undo, as a word typed is. */
export const UNDO_GROUP_MS = 800;
const UNDO_STEPS = 60;

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
  /** The shared library, which templates read as vars.<key>, text.<key> and lookup(). */
  library = $state<LibraryEntry[]>([]);
  /** Custom fields, which templates read as customer.custom.<key> and project.custom.<key>. */
  customFields = $state<CustomField[]>([]);

  /** Whether there's a change to undo, or an undone one to redo. */
  canUndo = $state(false);
  canRedo = $state(false);

  revision = 0;
  #saved = "";
  #seen = "";
  // The content before each step of changes, newest last, and what's been undone.
  #before: string[] = [];
  #undone: string[] = [];
  #changedAt = 0;
  #stepping = false;
  // When this look at the template began: the sample report's start, to the minute.
  #started = thisMinute();
  #saveTimer: ReturnType<typeof setTimeout> | undefined;
  #checkTimer: ReturnType<typeof setTimeout> | undefined;
  #saving: Promise<void> | null = null;

  get id(): number {
    return this.template?.id ?? 0;
  }

  get assets(): string[] {
    return this.template?.assets.map((a) => a.sha256) ?? [];
  }

  /** The names besides the answers and the built-in context: the library's and custom fields'. */
  get libraryNames(): Record<string, string> {
    return { ...libraryNames(this.library), ...customNames(this.customFields) };
  }

  /** The library as plain data, which can be sent to the expression worker. */
  get #plainLibrary(): LibraryEntry[] {
    return $state.snapshot(this.library) as LibraryEntry[];
  }

  /** What each library name is, for the rule editors. */
  get libraryLabels(): Record<string, string> {
    return { ...libraryLabels(this.library), ...customLabels(this.customFields) };
  }

  /**
   * The sample context, custom fields' examples included. The sample report is this
   * template's: titled with its name (a report's title until the technician changes
   * it), numbered with its prefix, and started now, so a question that starts as the
   * moment the report is started shows today.
   */
  get sampleContext(): Record<string, Record<string, unknown>> {
    const fields = $state.snapshot(this.customFields) as CustomField[];
    const context = sampleContext({ customer: sampleCustom(fields, "customer"), project: sampleCustom(fields, "project") });
    context.report.started = this.#started;
    if (this.template) context.report.title = this.template.name;
    if (this.content) context.report.number = String(context.report.number).replace(/^[A-Z]+/, this.content.settings.prefix);
    return context;
  }

  /** The library as the preview reads it. */
  get libraryPreview() {
    return { names: this.libraryNames, ...libraryValues(this.#plainLibrary) };
  }

  async load(id: number): Promise<void> {
    clearTimeout(this.#saveTimer);
    try {
      [this.library, this.customFields] = await Promise.all([libraryApi.list().catch(() => []), customFieldsApi.list().catch(() => [])]);
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
    this.#before = [];
    this.#undone = [];
    this.canUndo = this.canRedo = false;
    this.saveState = "saved";
    this.saveMessage = null;
    this.problems = check(content, { assets: this.assets, library: this.libraryNames });
  }

  /** Called with the content's JSON whenever it may have changed. */
  noticed(text: string): void {
    if (text === this.#seen || this.content === null) {
      this.#stepping = false;
      return;
    }
    if (this.#stepping) {
      this.#stepping = false;
    } else if (!this.readonly) {
      // A new step to undo, unless it follows the last change at once (typing).
      const now = Date.now();
      if (now - this.#changedAt > UNDO_GROUP_MS || !this.#before.length) {
        this.#before.push(this.#seen);
        if (this.#before.length > UNDO_STEPS) this.#before.shift();
      }
      this.#changedAt = now;
      this.#undone = [];
      this.canUndo = true;
      this.canRedo = false;
    }
    this.#seen = text;
    clearTimeout(this.#checkTimer);
    this.#checkTimer = setTimeout(() => {
      if (this.content) this.problems = check($state.snapshot(this.content) as TemplateContent, { assets: this.assets, library: this.libraryNames });
    }, CHECK_AFTER_MS);
    if (this.readonly || this.saveState === "conflict") return;
    if (text !== this.#saved) {
      this.saveState = "unsaved";
      clearTimeout(this.#saveTimer);
      this.#saveTimer = setTimeout(() => void this.save(), SAVE_AFTER_MS);
    } else if (!this.#saving) {
      // Back to what's saved (a change the server refused, taken back): nothing to send.
      clearTimeout(this.#saveTimer);
      this.saveState = "saved";
      this.saveMessage = null;
    }
  }

  /**
   * Call just before removing something: the removal is a step of its own to undo, and
   * a note says what went, with Undo on it.
   */
  removing(what: string): void {
    this.#changedAt = 0;
    // The removal will be the step after these; the note's Undo takes back that one,
    // and says so if other changes have come since.
    const steps = this.#before.length + 1;
    toast(`Removed ${what}.`, "info", { key: "template-removed", lifetime: 12_000, action: { label: "Undo", run: () => {
      if (this.#before.length === steps) this.undo();
      else toast("Other changes came after that: step back to it with Undo (Ctrl+Z).", "info", { key: "template-removed", lifetime: 8000 });
    } } });
  }

  /** Takes back the last step of changes (a block removed, a word typed), or with `again` puts back the last one undone. */
  undo(again = false): void {
    const [from, to] = again ? [this.#undone, this.#before] : [this.#before, this.#undone];
    const text = from.pop();
    if (text === undefined || this.content === null || this.readonly) return;
    to.push(this.#seen);
    this.#stepping = true;
    this.#changedAt = 0;
    this.content = JSON.parse(text) as TemplateContent;
    this.canUndo = this.#before.length > 0;
    this.canRedo = this.#undone.length > 0;
    // What's selected may not be there any more.
    const selected = this.selection?.id;
    if (selected && !text.includes(`"id":"${selected}"`)) this.selection = null;
  }

  /** Saves now if anything is unsaved; waits for a save under way. */
  async save(): Promise<void> {
    clearTimeout(this.#saveTimer);
    // One save at a time: whoever waited looks again, since another waiter may have
    // started the next one (two sends of one revision would be refused as a conflict).
    while (this.#saving) await this.#saving;
    if (this.content === null || this.readonly || this.saveState === "conflict") return;
    const content = $state.snapshot(this.content) as TemplateContent;
    const text = JSON.stringify(content);
    if (text === this.#saved) {
      this.saveState = "saved";
      this.saveMessage = null;
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
    const mine = this.#saving;
    await mine;
    if (this.#saving === mine) this.#saving = null;
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

  /** Whether leaving now would lose changes: not yet saved, or refused by the server. */
  get unsaved(): boolean {
    return this.saveState === "unsaved" || this.saveState === "saving" || this.saveState === "failed";
  }
}

const KEY = Symbol("template-draft");

export function shareDraft(draft: Draft): void {
  setContext(KEY, draft);
}

export function useDraft(): Draft {
  return getContext<Draft>(KEY);
}
