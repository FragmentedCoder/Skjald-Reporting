import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "#lib/api.js";
import type { Question, Step } from "#lib/templates/types.js";
import type { Answers } from "./answers";
import type { Activity, Checkout, FormState, ReportDetail, ReportsApi, Saved } from "./api";
import { ReportEditor, SAVE_AFTER_MS } from "./editor.svelte";

const OPTIONS = [{ value: "low", label: "Low" }, { value: "high", label: "High" }];
const VECTOR = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H";
const NOW = "2026-10-24T12:00:00.000Z";

const question = (id: string, type: string, extra: Partial<Question> = {}): Question => ({
  id, key: id.slice(2), type, label: id, help: "", required: false, required_when: null, visible_when: null,
  default: null, valid_when: null, valid_message: "", value: null, settings: {}, ...extra,
});

const FORM: Step[] = [
  { id: "s_details", title: "Details", help: "", visible_when: null, questions: [
    question("q_title", "text", { required: true }),
    // Starts as "low" by its rule.
    question("q_severity", "dropdown", { default: '"low"', settings: { options: OPTIONS } }),
    question("q_cvss", "cvss"),
  ] },
  { id: "s_access", title: "Access", help: "", visible_when: null, questions: [
    question("q_password", "secret"),
    question("q_lead", "person", { settings: { who: "team" } }),
    question("q_witness", "signature"),
  ] },
];
const Q = Object.fromEntries(FORM.flatMap((s) => s.questions).map((q) => [q.id, q]));
const NOTHING: FormState = { hidden: [], required: [], invalid: {}, missing: [], errors: [] };

/**
 * A stand-in for the server, keeping one report as backend/app/reports does: an answer
 * is taken only in a step the caller holds, a CVSS score, a person's details and a
 * signature's moment are the server's own, a secret is given out masked, and an empty
 * answer is forgotten or kept as cleared. "me" is the browser under test.
 */
class Server {
  answers: Answers = {};
  saves = 0;
  checkouts: Checkout[] = [];
  title = "Security incident report";
  mayEdit = true;
  /** Every call, as "name" and what was sent. */
  calls: [string, unknown][] = [];
  /** What the next save is refused with. */
  refuse: ApiError | null = null;
  /** Held back until let go: a save that takes a while. */
  slow: Promise<void> | null = null;
  missing: FormState["missing"] = [];
  #nextCheckout = 1;

  hold(step: string | null, mine = true, name = mine ? "Astrid Fjeld" : "Bo Berg"): Checkout {
    const checkout = { id: this.#nextCheckout++, step, holder: { id: mine ? 4 : 5, name }, taken_at: NOW, active_at: NOW, stale: false, mine };
    this.checkouts = [...this.checkouts, checkout];
    return checkout;
  }

  /** Someone else saves an answer, in a step of their own. */
  others(answers: Answers): void {
    this.answers = { ...this.answers, ...answers };
    this.saves++;
  }

  #shown(answers: Answers): Answers {
    return Object.fromEntries(Object.entries(answers).map(([id, value]) =>
      [id, Q[id].type === "secret" && typeof value === "string" ? { masked: true, printed: `${value.slice(0, 2)}••••••${value.slice(-2)}` } : value]));
  }

  #activity(): Activity {
    return { status: "draft", saves: this.saves, updated_at: NOW, checkouts: this.checkouts };
  }

  #detail(): ReportDetail {
    return {
      id: 7, number: "INC-2026-0001", title: this.title, status: "draft", revision: 1,
      project: { id: 3, number: "P-2026-10-001", name: "Portal brute force", classification: "TLP:AMBER", archived: false },
      customer: { id: 2, name: "Fjordvik Logistik A/S" },
      template: { id: 1, name: "Security incident report", version: 1, content: { schema: 1, settings: { prefix: "INC" } as never, form: FORM, layout: [] } },
      site: null, sites: [], author: { id: 4, name: "Astrid Fjeld" }, created_at: NOW, updated_at: NOW,
      answers: this.#shown(this.answers), saves: this.saves, context: {}, library: { names: {}, values: {}, tables: {} }, people: [], assets: {},
      time_zone: "Europe/Copenhagen", checkouts: this.checkouts, may_edit: this.mayEdit, may_reveal: true, may_break: false, may_discard: true,
      state: { ...NOTHING, missing: this.missing },
    };
  }

  #save(given: Answers): Saved {
    const held = (step: string) => this.checkouts.some((c) => c.mine && (c.step === null || c.step === step));
    for (const id of Object.keys(given)) {
      const step = FORM.find((s) => s.questions.some((q) => q.id === id));
      if (!step || !held(step.id)) throw new ApiError(409, "Check the step out before changing its answers.");
    }
    const next = { ...this.answers };
    const changed: string[] = [];
    for (const [id, value] of Object.entries(given)) {
      const before = JSON.stringify(next[id]);
      if (value === null) {
        if (Q[id].default) next[id] = null;
        else delete next[id];
      } else if (Q[id].type === "cvss") {
        next[id] = { vector: (value as { vector: string }).vector.trim(), score: 9.8, severity: "Critical" };
      } else if (Q[id].type === "person") {
        next[id] = { id: (value as { id: string }).id, display_name: "Bo Berg", job_title: "Consultant" };
      } else if (Q[id].type === "signature") {
        const kept = next[id] as { name: string; at: string } | undefined;
        const name = (value as { name: string }).name.trim();
        next[id] = { name, confirmed: true, at: kept?.name === name ? kept.at : NOW };
      } else {
        next[id] = value;
      }
      if (JSON.stringify(next[id]) !== before) changed.push(id);
    }
    this.answers = next;
    if (changed.length) this.saves++;
    return {
      saves: this.saves, updated_at: NOW,
      answers: this.#shown(Object.fromEntries(changed.filter((id) => id in next).map((id) => [id, next[id]]))),
      forgotten: changed.filter((id) => !(id in next)),
    };
  }

  /** What was sent with each call of this name. */
  sent(name: string): unknown[] {
    return this.calls.filter(([called]) => called === name).map(([, body]) => body);
  }

  readonly api = {
    get: async () => {
      this.calls.push(["get", null]);
      return structuredClone(this.#detail());
    },
    save: async (_id: number, answers: Answers) => {
      this.calls.push(["save", structuredClone(answers)]);
      if (this.slow) await this.slow;
      if (this.refuse) {
        const error = this.refuse;
        this.refuse = null;
        throw error;
      }
      return structuredClone(this.#save(answers));
    },
    activity: async () => {
      this.calls.push(["activity", null]);
      return structuredClone(this.#activity());
    },
    check: async () => {
      this.calls.push(["check", null]);
      return { ...NOTHING, missing: this.missing };
    },
    checkOut: async (_id: number, step: string | null) => {
      this.calls.push(["checkOut", step]);
      const other = this.checkouts.find((c) => !c.mine && (step === null || c.step === null || c.step === step));
      if (other) throw new ApiError(409, `${other.holder.name} has the step “Details” checked out.`);
      this.hold(step);
      return structuredClone(this.#activity());
    },
    release: async (_id: number, checkout: number) => {
      this.calls.push(["release", checkout]);
      this.checkouts = this.checkouts.filter((c) => c.id !== checkout);
      return structuredClone(this.#activity());
    },
    update: async (_id: number, change: { title?: string }) => {
      this.calls.push(["update", change]);
      if (change.title) this.title = change.title;
      return structuredClone(this.#detail());
    },
    discard: async (_id: number, confirmNumber: string) => {
      this.calls.push(["discard", confirmNumber]);
    },
  } as unknown as ReportsApi;
}

/** The report open in the editor, with these checkouts of one's own. */
async function open(server: Server): Promise<ReportEditor> {
  const editor = new ReportEditor(server.api);
  await editor.load(7);
  return editor;
}

/** Until the answers changed last are saved, and the reply taken in. */
const afterSaving = () => vi.advanceTimersByTimeAsync(SAVE_AFTER_MS);

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("opening a report", () => {
  it("takes the answers as the server keeps them, with nothing to save", async () => {
    const server = new Server();
    server.answers = { q_title: "Portal brute force", q_password: "Sommer2026!Fjord" };
    const editor = await open(server);
    expect(editor.answers).toEqual({ q_title: "Portal brute force", q_password: { masked: true, printed: "So••••••rd" } });
    expect(editor.unsaved).toBe(false);
    expect(editor.saveState).toBe("saved");
    // The template as the preview reads it: a report has no sample answers.
    expect(editor.content?.sample).toEqual({ answers: {} });
    await afterSaving();
    expect(server.sent("save")).toEqual([]);
  });

  it("says why a report can't be opened", async () => {
    const server = new Server();
    server.api.get = async () => {
      throw new ApiError(404, "That report doesn't exist.");
    };
    const editor = await open(server);
    expect(editor.report).toBeNull();
    expect(editor.loadError).toBe("That report doesn't exist.");
  });
});

describe("saving as you type", () => {
  it("saves a second after the last change, and sends only what changed", async () => {
    const server = new Server();
    server.answers = { q_title: "Portal", q_severity: "high" };
    server.hold(null);
    const editor = await open(server);

    editor.set(Q.q_title, "Portal brute");
    expect(editor.saveState).toBe("unsaved");
    expect(editor.unsaved).toBe(true);
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS - 100);
    editor.set(Q.q_title, "Portal brute force");
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS - 100);
    // Still typing: nothing sent yet.
    expect(server.sent("save")).toEqual([]);
    await vi.advanceTimersByTimeAsync(100);

    expect(server.sent("save")).toEqual([{ q_title: "Portal brute force" }]);
    expect(editor.saveState).toBe("saved");
    expect(editor.savedAt).toBe(NOW);
    expect(editor.unsaved).toBe(false);
    // Nothing more to send.
    await afterSaving();
    expect(server.sent("save")).toHaveLength(1);
  });

  it("sends only the answers in the steps this person holds", async () => {
    const server = new Server();
    server.hold("s_details");
    const editor = await open(server);
    expect(editor.mayChange("s_details")).toBe(true);
    expect(editor.mayChange("s_access")).toBe(false);

    editor.set(Q.q_title, "In my step");
    editor.set(Q.q_password, "hunter2hunter2");
    await afterSaving();
    expect(server.sent("save")).toEqual([{ q_title: "In my step" }]);
    // What's in the other step waits for its checkout, and leaving would lose it.
    expect(editor.stranded.map((c) => c.question.id)).toEqual(["q_password"]);
    expect(editor.unsaved).toBe(true);

    await editor.checkOut("s_access");
    await afterSaving();
    expect(server.sent("save")).toEqual([{ q_title: "In my step" }, { q_password: "hunter2hunter2" }]);
    expect(editor.stranded).toEqual([]);
    expect(editor.unsaved).toBe(false);
  });

  it("sends an emptied answer as null: forgotten, or kept as cleared when it would start as something", async () => {
    const server = new Server();
    server.answers = { q_title: "Portal", q_severity: "high", q_cvss: { vector: VECTOR, score: 9.8, severity: "Critical" } };
    server.hold(null);
    const editor = await open(server);

    editor.set(Q.q_title, "");
    editor.set(Q.q_severity, null);
    editor.set(Q.q_cvss, { vector: "", score: 0, severity: "" });
    // Here at once as the server will keep them.
    expect(editor.answers).toEqual({ q_severity: null });
    await afterSaving();
    expect(server.sent("save")).toEqual([{ q_title: null, q_severity: null, q_cvss: null }]);
    expect(server.answers).toEqual({ q_severity: null });
    expect(editor.answers).toEqual({ q_severity: null });
    expect(editor.unsaved).toBe(false);
  });

  it("doesn't save what a question merely starts as", async () => {
    const server = new Server();
    server.hold(null);
    const editor = await open(server);
    // The form shows "low" for the severity, from its rule; nothing was set.
    await afterSaving();
    expect(server.sent("save")).toEqual([]);
    expect(editor.answers).toEqual({});
  });

  it("saves at once when asked, without waiting for the second to pass", async () => {
    const server = new Server();
    server.hold(null);
    const editor = await open(server);
    editor.set(Q.q_title, "Portal");
    await editor.save();
    expect(server.sent("save")).toEqual([{ q_title: "Portal" }]);
    await afterSaving();
    expect(server.sent("save")).toHaveLength(1);
  });
});

describe("what the server kept", () => {
  it("takes the place of what was typed: a score worked out, a person's details, a signature's moment, a secret masked", async () => {
    const server = new Server();
    server.hold(null);
    const editor = await open(server);

    editor.set(Q.q_cvss, { vector: VECTOR, score: 1, severity: "Low" });
    editor.set(Q.q_lead, { id: "5", technician: true, reviewer: false, on_team: true, display_name: "Somebody Else" });
    editor.set(Q.q_witness, { name: "Mette Lund", confirmed: true, at: "1999-01-01T00:00:00Z" });
    editor.set(Q.q_password, "Sommer2026!Fjord");
    await afterSaving();

    expect(server.sent("save")).toEqual([{
      q_cvss: { vector: VECTOR, score: 1, severity: "Low" },
      // A person goes by ID alone; a secret as it was typed.
      q_lead: { id: "5" },
      q_witness: { name: "Mette Lund", confirmed: true, at: "1999-01-01T00:00:00Z" },
      q_password: "Sommer2026!Fjord",
    }]);
    expect(editor.answers).toEqual({
      q_cvss: { vector: VECTOR, score: 9.8, severity: "Critical" },
      q_lead: { id: "5", display_name: "Bo Berg", job_title: "Consultant" },
      q_witness: { name: "Mette Lund", confirmed: true, at: NOW },
      q_password: { masked: true, printed: "So••••••rd" },
    });
    expect(editor.unsaved).toBe(false);
    // The typed secret is nowhere in what the editor holds.
    expect(JSON.stringify(editor.answers)).not.toContain("Sommer2026");
  });

  it("shows what the server kept already, when the save changed nothing there", async () => {
    const server = new Server();
    server.answers = { q_witness: { name: "Mette Lund", confirmed: true, at: "2026-10-20T08:00:00.000Z" } };
    server.hold(null);
    const editor = await open(server);
    // The same name confirmed again: the signature keeps its first moment.
    editor.set(Q.q_witness, { name: "Mette Lund", confirmed: true, at: NOW });
    await afterSaving();
    expect(server.sent("save")).toHaveLength(1);
    expect(editor.answers.q_witness).toEqual({ name: "Mette Lund", confirmed: true, at: "2026-10-20T08:00:00.000Z" });
    expect(editor.unsaved).toBe(false);
    await afterSaving();
    expect(server.sent("save")).toHaveLength(1);
  });

  it("leaves what was typed while the save was under way, and saves that next", async () => {
    const server = new Server();
    server.hold(null);
    const editor = await open(server);
    let letGo = () => {};
    server.slow = new Promise((done) => (letGo = done));

    editor.set(Q.q_password, "Sommer");
    await afterSaving();
    expect(editor.saveState).toBe("saving");
    editor.set(Q.q_password, "Sommer2026!Fjord");
    editor.set(Q.q_title, "Portal");
    server.slow = null;
    letGo();
    await vi.advanceTimersByTimeAsync(0);
    // The first save's reply (the shorter secret, masked) didn't replace what's being typed.
    expect(editor.answers.q_password).toBe("Sommer2026!Fjord");
    expect(editor.saveState).toBe("unsaved");

    await afterSaving();
    expect(server.sent("save")).toEqual([{ q_password: "Sommer" }, { q_password: "Sommer2026!Fjord", q_title: "Portal" }]);
    expect(editor.answers).toEqual({ q_title: "Portal", q_password: { masked: true, printed: "So••••••rd" } });
    expect(editor.saveState).toBe("saved");
  });
});

describe("a save that's refused", () => {
  it("says why, keeps what was typed, and tries again once it's changed", async () => {
    const server = new Server();
    server.answers = { q_title: "Portal" };
    server.hold(null);
    const editor = await open(server);
    server.refuse = new ApiError(400, "“q_title” takes at most 10,000 characters.");

    editor.set(Q.q_title, "Far too long");
    await afterSaving();
    expect(editor.saveState).toBe("refused");
    expect(editor.saveMessage).toBe("“q_title” takes at most 10,000 characters.");
    expect(editor.answers.q_title).toBe("Far too long");
    expect(editor.unsaved).toBe(true);
    // Not tried again by itself.
    await afterSaving();
    await editor.poll();
    await afterSaving();
    expect(server.sent("save")).toHaveLength(1);

    editor.set(Q.q_title, "Shorter");
    expect(editor.saveState).toBe("unsaved");
    expect(editor.saveMessage).toBeNull();
    await afterSaving();
    expect(server.sent("save")).toEqual([{ q_title: "Far too long" }, { q_title: "Shorter" }]);
    expect(editor.saveState).toBe("saved");
  });

  it("is tried again when Skjald is reached again", async () => {
    const server = new Server();
    server.hold(null);
    const editor = await open(server);
    server.refuse = new ApiError(0, "Skjald could not be reached. Check your connection and try again.");
    editor.set(Q.q_title, "Portal");
    await afterSaving();
    expect(editor.saveState).toBe("failed");
    expect(editor.saveMessage).toBe("Skjald could not be reached. Check your connection and try again.");

    await editor.poll();
    await afterSaving();
    expect(editor.saveState).toBe("saved");
    expect(server.answers).toEqual({ q_title: "Portal" });
  });

  it("says the checkout was ended, shows who holds what now, and saves once the step is checked out again", async () => {
    const server = new Server();
    const mine = server.hold("s_details");
    const editor = await open(server);
    editor.set(Q.q_title, "Before");
    await afterSaving();

    // An Administrator ends the checkout, and someone else takes the other step.
    server.checkouts = server.checkouts.filter((c) => c.id !== mine.id);
    server.hold("s_access", false);
    editor.set(Q.q_title, "After");
    await afterSaving();

    expect(editor.saveState).toBe("lost");
    expect(editor.saveMessage).toBe("Your checkout was ended, so your last changes aren't saved. Check the step out again to save them.");
    expect(editor.checkouts.map((c) => [c.step, c.holder.name])).toEqual([["s_access", "Bo Berg"]]);
    expect(editor.mayChange("s_details")).toBe(false);
    // What was typed is kept, and waits.
    expect(editor.answers.q_title).toBe("After");
    expect(editor.stranded.map((c) => c.question.id)).toEqual(["q_title"]);
    expect(server.answers).toEqual({ q_title: "Before" });

    await editor.checkOut("s_details");
    await afterSaving();
    expect(server.answers).toEqual({ q_title: "After" });
    expect(editor.saveState).toBe("saved");
    expect(editor.saveMessage).toBeNull();
  });

  it("says the server's reason when the report can't be changed any more", async () => {
    const server = new Server();
    server.hold(null);
    const editor = await open(server);
    server.mayEdit = false;
    server.refuse = new ApiError(409, "Archived projects are read-only.");
    editor.set(Q.q_title, "Late");
    await afterSaving();
    expect(editor.saveState).toBe("lost");
    expect(editor.saveMessage).toBe("Archived projects are read-only.");
    expect(editor.report?.may_edit).toBe(false);
    expect(editor.mayChange("s_details")).toBe(false);
  });

  it("can be dropped: the answers go back to what the server keeps", async () => {
    const server = new Server();
    server.answers = { q_title: "Portal" };
    const editor = await open(server);
    editor.set(Q.q_title, "Typed without a checkout");
    editor.set(Q.q_password, "hunter2hunter2");
    expect(editor.stranded).toHaveLength(2);
    editor.drop(editor.stranded.map((c) => c.question));
    expect(editor.answers).toEqual({ q_title: "Portal" });
    expect(editor.unsaved).toBe(false);
    expect(editor.saveState).toBe("saved");
  });
});

describe("other people's work", () => {
  it("shows who holds what at each look", async () => {
    const server = new Server();
    const editor = await open(server);
    expect(editor.checkouts).toEqual([]);
    server.hold("s_access", false);
    await editor.poll();
    expect(editor.checkouts.map((c) => [c.step, c.holder.name, c.mine])).toEqual([["s_access", "Bo Berg", false]]);
    // Nobody saved: the report isn't fetched again.
    expect(server.sent("get")).toHaveLength(1);
  });

  it("fetches the report again when someone else saved, and takes their answers around its own unsaved ones", async () => {
    const server = new Server();
    server.answers = { q_title: "Portal" };
    server.hold("s_details");
    server.hold("s_access", false);
    const editor = await open(server);

    editor.set(Q.q_title, "Portal brute force");
    server.others({ q_password: "bo's secret value", q_lead: { id: "5", display_name: "Bo Berg", job_title: "Consultant" } });
    await editor.poll();

    expect(server.sent("get")).toHaveLength(2);
    expect(editor.answers).toEqual({
      q_title: "Portal brute force",
      q_password: { masked: true, printed: "bo••••••ue" },
      q_lead: { id: "5", display_name: "Bo Berg", job_title: "Consultant" },
    });
    // Its own change is still saved, and theirs isn't sent back.
    await afterSaving();
    expect(server.sent("save")).toEqual([{ q_title: "Portal brute force" }]);
    expect(editor.unsaved).toBe(false);
  });

  it("counts its own saves: they don't make it fetch the report again", async () => {
    const server = new Server();
    server.hold(null);
    const editor = await open(server);
    editor.set(Q.q_title, "One");
    await afterSaving();
    editor.set(Q.q_title, "Two");
    await afterSaving();
    await editor.poll();
    expect(server.saves).toBe(2);
    expect(server.sent("get")).toHaveLength(1);
  });

  it("tells someone else's save from its own, though both came between two looks", async () => {
    const server = new Server();
    server.hold("s_details");
    server.hold("s_access", false);
    const editor = await open(server);
    server.others({ q_password: "bo's secret value" });
    editor.set(Q.q_title, "Mine");
    await afterSaving();
    // Its own save doesn't fetch the report: two people typing at once would fetch it at every save.
    expect(server.sent("get")).toHaveLength(1);
    expect(editor.answers).toEqual({ q_title: "Mine" });
    // The next look does, since the report was saved once more than this browser saved it.
    await editor.poll();
    expect(server.sent("get")).toHaveLength(2);
    expect(editor.answers).toEqual({ q_title: "Mine", q_password: { masked: true, printed: "bo••••••ue" } });
    // And then it's level again.
    await editor.poll();
    expect(server.sent("get")).toHaveLength(2);
  });

  it("waits for a save under way before it looks, so an older answer never comes back", async () => {
    const server = new Server();
    server.hold("s_details");
    const editor = await open(server);
    let letGo = () => {};
    server.slow = new Promise((done) => (letGo = done));
    editor.set(Q.q_title, "Typed");
    await afterSaving();
    server.others({ q_password: "bo's secret value" });
    const looked = editor.poll();
    await vi.advanceTimersByTimeAsync(0);
    // The look hasn't started: the save comes first.
    expect(server.sent("activity")).toEqual([]);
    server.slow = null;
    letGo();
    await looked;
    expect(editor.answers).toEqual({ q_title: "Typed", q_password: { masked: true, printed: "bo••••••ue" } });
    expect(editor.unsaved).toBe(false);
  });

  it("says so when the report is gone", async () => {
    const server = new Server();
    const editor = await open(server);
    server.api.activity = async () => {
      throw new ApiError(404, "That report doesn't exist.");
    };
    await editor.poll();
    expect(editor.gone).toBe(true);
    expect(editor.loadError).toBe("That report doesn't exist.");
  });
});

describe("checking out and releasing", () => {
  it("says who's in the way, and shows who holds what", async () => {
    const server = new Server();
    const editor = await open(server);
    server.hold("s_details", false);
    await expect(editor.checkOut("s_details")).rejects.toMatchObject({ status: 409, message: "Bo Berg has the step “Details” checked out." });
    expect(editor.checkouts.map((c) => c.holder.name)).toEqual(["Bo Berg"]);
    expect(editor.holding).toBe(false);
  });

  it("takes other people's answers when a step is checked out after they saved in it", async () => {
    const server = new Server();
    const editor = await open(server);
    server.others({ q_title: "Bo's title" });
    await editor.checkOut("s_details");
    expect(editor.answers).toEqual({ q_title: "Bo's title" });
    expect(editor.holding).toBe(true);
  });

  it("saves at once when a step is released", async () => {
    const server = new Server();
    const mine = server.hold("s_details");
    const editor = await open(server);
    editor.set(Q.q_title, "Just typed");
    await editor.release(mine);
    expect(server.calls.map(([name]) => name).slice(-2)).toEqual(["save", "release"]);
    expect(server.answers).toEqual({ q_title: "Just typed" });
    expect(editor.checkouts).toEqual([]);
    expect(editor.unsaved).toBe(false);
  });

  it("keeps the checkout when what was typed can't be saved", async () => {
    const server = new Server();
    const mine = server.hold("s_details");
    const editor = await open(server);
    server.refuse = new ApiError(400, "“q_title” takes text.");
    editor.set(Q.q_title, "Odd");
    await expect(editor.release(mine)).rejects.toMatchObject({ message: "“q_title” takes text." });
    expect(server.sent("release")).toEqual([]);
    expect(editor.checkouts).toHaveLength(1);
    expect(editor.answers.q_title).toBe("Odd");
  });

  it("changes the title under a checkout, keeping what isn't saved yet", async () => {
    const server = new Server();
    server.hold("s_details");
    const editor = await open(server);
    editor.set(Q.q_title, "Typing");
    await editor.update({ title: "Brute force, October" });
    expect(editor.report?.title).toBe("Brute force, October");
    expect(editor.answers.q_title).toBe("Typing");
  });
});

describe("checking the answers", () => {
  it("saves what's pending, then asks the server what's missing", async () => {
    const server = new Server();
    server.hold(null);
    server.missing = [{ step: "s_details", question: "q_title", message: "is required." }];
    const editor = await open(server);
    expect(editor.verdict?.missing).toHaveLength(1);
    expect(editor.checked).toBe(false);

    editor.set(Q.q_severity, "high");
    await editor.check();
    expect(server.calls.map(([name]) => name).slice(-2)).toEqual(["save", "check"]);
    expect(editor.checked).toBe(true);
    expect(editor.verdict?.missing).toEqual([{ step: "s_details", question: "q_title", message: "is required." }]);
  });

  it("asks again after each save, so the list follows the answers", async () => {
    const server = new Server();
    server.hold(null);
    server.missing = [{ step: "s_details", question: "q_title", message: "is required." }];
    const editor = await open(server);
    await editor.check();
    server.missing = [];
    editor.set(Q.q_title, "Portal brute force");
    await afterSaving();
    expect(editor.verdict?.missing).toEqual([]);
    expect(server.sent("check")).toHaveLength(2);
  });
});

describe("discarding", () => {
  it("sends the number typed, and leaves nothing to warn about", async () => {
    const server = new Server();
    server.hold(null);
    const editor = await open(server);
    editor.set(Q.q_title, "Never mind");
    await editor.discard("INC-2026-0001");
    expect(server.sent("discard")).toEqual(["INC-2026-0001"]);
    expect(editor.unsaved).toBe(false);
    await afterSaving();
    expect(server.sent("save")).toEqual([]);
  });
});
