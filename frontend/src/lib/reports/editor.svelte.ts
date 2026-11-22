// The report open in the editor: its answers as this browser has them, saved a moment
// after each change, and who has what checked out.
//
// Only the answers that changed are sent, and only those in steps this person holds, so
// two people working in different steps never overwrite each other. The server answers
// with the answers as it kept them (a CVSS score worked out, a picked person's details,
// a signature's moment, a secret masked), and those take the place of what was typed.
// Now and then the editor asks whether anyone else saved (the report counts its saves,
// and the editor counts its own); when they did, it fetches the report again and takes
// their answers, keeping its own that aren't saved yet.
//
// Everything that talks to the server about the answers goes through one queue, one at
// a time: a save never crosses a fetch, so an older reply can't undo a newer one.

import { ApiError, sessionGone } from "#lib/api.js";
import type { Id, Question, TemplateContent } from "#lib/templates/types.js";
import { copy, differs, held, merged, same, toSave, unsaved, type Answers } from "./answers";
import { holds, reportsApi, type Activity, type Checkout, type FormState, type ReportDetail, type ReportsApi, type Saved } from "./api";

/** How long after the last change the answers are saved. */
export const SAVE_AFTER_MS = 1000;
/** How often an open report asks who holds what and whether anyone saved. */
export const POLL_EVERY_MS = 20_000;

/**
 * Where the answers stand: all saved, changed and about to be saved, being saved, or
 * not saved: refused by the server (one answer can't be kept), not reached, or lost
 * with the checkout (someone ended it).
 */
export type SaveState = "saved" | "unsaved" | "saving" | "refused" | "failed" | "lost";

const CHECKOUT_ENDED = "Your checkout was ended, so your last changes aren't saved. Check the step out again to save them.";

export class ReportEditor {
  /** The report as last fetched. Its answers are in `answers`, and who holds what in `checkouts`. */
  report = $state.raw<ReportDetail | null>(null);
  /** The pinned template, as the form and the preview read it. It never changes while the report is open. */
  content = $state.raw<TemplateContent | null>(null);
  /** The answers as this browser has them: the server's, and what's been changed here since. */
  answers = $state<Answers>({});
  checkouts = $state.raw<Checkout[]>([]);
  loadError = $state<string | null>(null);
  /** The report was discarded, or isn't this person's to open any more. */
  gone = $state(false);

  saveState = $state<SaveState>("saved");
  /** Why the last save didn't keep the answers, in a sentence fit to show. */
  saveMessage = $state<string | null>(null);
  /** When this browser last saved something. */
  savedAt = $state<string | null>(null);

  /** The server's verdict on the answers as it keeps them: from the report, or the last check. */
  verdict = $state.raw<FormState | null>(null);
  /** The technician asked for the answers to be checked: the list of what's missing shows, and stays current. */
  checked = $state(false);
  checking = $state(false);

  readonly #api: ReportsApi;
  /** The answers as the server keeps them, as far as this browser knows. */
  #kept = $state.raw<Answers>({});
  /** How many of the report's saves this browser has seen: its own, and others' as of the last fetch. */
  #seen = 0;
  #timer: ReturnType<typeof setTimeout> | undefined;
  #queue: Promise<unknown> = Promise.resolve();
  #closed = false;

  constructor(api: ReportsApi = reportsApi) {
    this.#api = api;
  }

  /** The questions whose answers changed here and aren't saved yet, each with its step. */
  readonly changed: { step: Id; question: Question }[] = $derived(this.content ? unsaved(this.content.form, this.answers, this.#kept) : []);

  /** Changed answers in steps this person doesn't hold (any more): they can't be saved until the step is checked out again. */
  readonly stranded: { step: Id; question: Question }[] = $derived(this.changed.filter((c) => !holds(this.checkouts, c.step)));

  /** Whether leaving now would lose something typed here. */
  get unsaved(): boolean {
    return !this.#closed && (this.changed.length > 0 || this.saveState === "saving");
  }

  /** Whether this person holds anything of the report: what changing its title or site takes. */
  get holding(): boolean {
    return this.checkouts.some((c) => c.mine);
  }

  /** Whether this person may change the step's answers now: they hold it, or the whole report. */
  mayChange(step: Id): boolean {
    return (this.report?.may_edit ?? false) && holds(this.checkouts, step);
  }

  async load(id: number): Promise<void> {
    try {
      const report = await this.#api.get(id);
      this.content = { ...report.template.content, sample: { answers: {} } };
      this.#take(report);
      this.loadError = null;
    } catch (error) {
      if (!sessionGone(error)) this.loadError = error instanceof ApiError ? error.message : "The report couldn't be loaded.";
    }
  }

  /** The technician changed an answer: it's saved a moment later, if its step is held. */
  set(question: Question, value: unknown): void {
    const next = held(question, value);
    if (next === undefined) delete this.answers[question.id];
    else this.answers[question.id] = next;
    this.#settle(true);
  }

  /** Puts back what the server keeps for these questions, dropping what was changed here. */
  drop(questions: Question[]): void {
    const kept = copy(this.#kept);
    for (const { id } of questions) {
      if (kept[id] === undefined) delete this.answers[id];
      else this.answers[id] = kept[id];
    }
    this.#settle(true);
  }

  /** Saves now whatever changed in the steps held; waits for a save under way. */
  save(): Promise<void> {
    clearTimeout(this.#timer);
    return this.#then(() => this.#save());
  }

  /**
   * Asks who holds what and whether anyone saved since; when they did, fetches the
   * report again and takes their answers. A failed look is tried again at the next one.
   */
  poll(): Promise<void> {
    return this.#then(async () => {
      const report = this.report;
      if (!report || this.gone || this.#closed) return;
      try {
        const activity = await this.#api.activity(report.id);
        // Reached again: what couldn't be sent before is tried once more.
        this.#noticed(activity, this.saveState === "failed");
        if (activity.saves > this.#seen || activity.status !== report.status) await this.#refresh();
      } catch (error) {
        this.#missing(error);
      }
    });
  }

  /** Polls while the page is in view, and on coming back to it. Returns the function that stops it. */
  watch(): () => void {
    const look = () => {
      if (document.visibilityState === "visible") void this.poll();
    };
    const timer = setInterval(look, POLL_EVERY_MS);
    document.addEventListener("visibilitychange", look);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", look);
    };
  }

  /** Checks out one step, or (null) the whole report. Refused with a sentence naming who is in the way. */
  checkOut(step: Id | null): Promise<void> {
    return this.#then(async () => {
      const id = this.#id();
      try {
        const activity = await this.#api.checkOut(id, step);
        // What waited for the step (typed under a checkout that was ended) is saved now.
        this.#noticed(activity, true);
        // Someone may have saved there since this browser last looked.
        if (activity.saves > this.#seen) await this.#refresh();
      } catch (error) {
        // Someone took it first: show who.
        if (error instanceof ApiError && error.status === 409) await this.#look();
        throw error;
      }
    });
  }

  /**
   * Releases one of this person's checkouts, once what was changed under it is saved.
   * If that can't be saved, the checkout is kept and the reason thrown, so nothing typed
   * is left where it can no longer be saved.
   */
  release(checkout: Checkout): Promise<void> {
    clearTimeout(this.#timer);
    return this.#then(async () => {
      await this.#save();
      // The save may have found the checkout ended already.
      if (!this.checkouts.some((c) => c.id === checkout.id)) return;
      if (this.changed.some((c) => checkout.step === null || checkout.step === c.step)) {
        throw new ApiError(0, this.saveMessage ?? "Some changes here couldn't be saved, so it's still checked out.");
      }
      try {
        this.#noticed(await this.#api.release(this.#id(), checkout.id));
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) await this.#look();
        else throw error;
      }
    });
  }

  /** Ends someone else's checkout (Administrators). What they saved is kept, and they're told by email. */
  endCheckout(checkout: Checkout): Promise<void> {
    return this.#then(async () => {
      try {
        this.#noticed(await this.#api.endCheckout(this.#id(), checkout.id));
      } catch (error) {
        // Ended already, by its holder or someone else.
        if (error instanceof ApiError && error.status === 404) await this.#look();
        else throw error;
      }
    });
  }

  /** Changes the title or the site: for someone holding a checkout. */
  update(change: { title?: string; site_id?: number | null }): Promise<void> {
    return this.#then(async () => this.#take(await this.#api.update(this.#id(), change)));
  }

  /** Saves what's pending, then asks the server what keeps the report from going for review. */
  check(): Promise<void> {
    clearTimeout(this.#timer);
    return this.#then(async () => {
      this.checking = true;
      try {
        await this.#save();
        this.verdict = await this.#api.check(this.#id());
        this.checked = true;
      } finally {
        this.checking = false;
      }
    });
  }

  /** Discards the draft, with its number typed to confirm. What wasn't saved goes with it. */
  discard(confirmNumber: string): Promise<void> {
    clearTimeout(this.#timer);
    return this.#then(async () => {
      await this.#api.discard(this.#id(), confirmNumber);
      this.close();
    });
  }

  /** Stops saving: the page is left, or the report is gone. A save under way finishes. */
  close(): void {
    clearTimeout(this.#timer);
    this.#closed = true;
  }

  #id(): number {
    if (!this.report) throw new ApiError(0, "The report isn't loaded yet.");
    return this.report.id;
  }

  /** Runs after everything asked before it, whether that worked or not. */
  #then<T>(job: () => Promise<T>): Promise<T> {
    const done = this.#queue.then(job);
    this.#queue = done.catch(() => undefined);
    return done;
  }

  async #save(): Promise<void> {
    const report = this.report;
    const content = this.content;
    if (!report || !content || this.#closed) return;
    const here = copy(this.answers);
    const sent = toSave(content.form, this.checkouts, here, this.#kept);
    if (!Object.keys(sent).length) {
      this.#settle(true);
      return;
    }
    this.saveState = "saving";
    try {
      const saved = await this.#api.save(report.id, sent);
      this.#keep(Object.keys(sent), here, saved);
      const mine = Object.keys(saved.answers).length + saved.forgotten.length > 0;
      if (mine) {
        this.savedAt = saved.updated_at;
        // Its own save is counted, and no more: if someone else saved meanwhile, the count
        // stays behind the server's, and the next look fetches their answers. (Not here:
        // two people typing at once would fetch the whole report at every save.)
        this.#seen += 1;
      }
      this.saveMessage = null;
      this.saveState = "saved";
      this.#settle(true);
      if (mine && this.checked) this.verdict = await this.#api.check(report.id).catch(() => this.verdict);
    } catch (error) {
      await this.#refused(error);
    }
  }

  /**
   * Takes in what a save kept. What's shown follows the server (the score it worked out,
   * the secret masked), unless the answer was changed again while the save was under way.
   */
  #keep(ids: Id[], before: Answers, saved: Saved): void {
    const kept = { ...this.#kept };
    for (const id of ids) {
      if (id in saved.answers) kept[id] = saved.answers[id];
      else if (saved.forgotten.includes(id)) delete kept[id];
      // Neither: the server already kept the same.
      if (differs(id, this.answers, before)) continue;
      if (kept[id] === undefined) delete this.answers[id];
      else if (kept[id] === null || !same(this.answers[id], kept[id])) this.answers[id] = kept[id];
    }
    // Its own copy: what's typed into the answers never reaches what the server is known to keep.
    this.#kept = copy(kept);
  }

  async #refused(error: unknown): Promise<void> {
    if (!(error instanceof ApiError) || sessionGone(error)) {
      this.saveState = "failed";
      this.saveMessage = error instanceof ApiError ? null : "The answers couldn't be saved.";
      return;
    }
    if (error.status === 409 || error.status === 403) {
      // The checkout is gone (an Administrator ended it), or the report isn't this
      // person's to change any more: who holds what, and what they may do, is fetched again.
      await this.#refresh();
      this.saveState = "lost";
      this.saveMessage = error.status === 409 && this.report?.may_edit ? CHECKOUT_ENDED : error.message;
    } else if (error.status === 404) {
      this.#missing(error);
    } else {
      // 400: one answer can't be kept, and nothing in that save was. What was typed stays, to be fixed.
      this.saveState = error.status === 0 || error.status >= 500 ? "failed" : "refused";
      this.saveMessage = error.message;
    }
  }

  /** Fetches the report again and takes it in. Failing, what's here stays as it is. */
  async #refresh(): Promise<void> {
    try {
      this.#take(await this.#api.get(this.#id(), true));
    } catch (error) {
      this.#missing(error);
    }
  }

  /** Fetches who holds what. */
  async #look(): Promise<void> {
    try {
      this.#noticed(await this.#api.activity(this.#id()));
    } catch (error) {
      this.#missing(error);
    }
  }

  /** The report as the server has it now: its answers taken in around what isn't saved here. */
  #take(report: ReportDetail): void {
    const form = this.content?.form ?? [];
    this.answers = merged(form, copy(this.answers), this.#kept, report.answers);
    this.#kept = copy(report.answers);
    this.#seen = report.saves;
    this.report = report;
    this.checkouts = report.checkouts;
    this.verdict = report.state;
    this.#settle(false);
  }

  /** Who holds what now. With `again`, a save that didn't go through before is tried again. */
  #noticed(activity: Activity, again = false): void {
    this.checkouts = activity.checkouts;
    this.#settle(again);
  }

  /** A report that's no longer there (discarded, or access to it ended) says so; other failures pass. */
  #missing(error: unknown): void {
    if (error instanceof ApiError && error.status === 404) {
      this.gone = true;
      this.loadError = error.message;
      this.close();
    }
  }

  /**
   * Works out where the answers stand, and saves soon when something waits in a step
   * that's held. After a change (`again`), a save that was refused is tried again; a
   * look at who holds what doesn't try one again by itself.
   */
  #settle(again: boolean): void {
    if (this.saveState === "saving" || this.#closed || !this.content) return;
    const waiting = Object.keys(toSave(this.content.form, this.checkouts, this.answers, this.#kept)).length > 0;
    const stopped = this.saveState === "refused" || this.saveState === "failed" || this.saveState === "lost";
    if (!this.changed.length) {
      clearTimeout(this.#timer);
      this.saveState = "saved";
      this.saveMessage = null;
    } else if (waiting && (again || !stopped)) {
      this.saveState = "unsaved";
      this.saveMessage = null;
      clearTimeout(this.#timer);
      this.#timer = setTimeout(() => void this.save(), SAVE_AFTER_MS);
    } else if (!stopped) {
      // Only answers in steps that aren't held: nothing to send.
      this.saveState = "unsaved";
    }
  }
}
