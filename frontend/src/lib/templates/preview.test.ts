import { describe, expect, it } from "vitest";
import incident from "../../../../shared/templates/incident.json";
import { paginate } from "./pages";
import { Engine } from "#lib/cel/engine.js";
import { peopleFor, preview, printValue, sampleContext, samplePeople, type PreviewInput, type Shown } from "./preview";
import type { TemplateContent } from "./types";

const content = () => structuredClone(incident) as unknown as TemplateContent;
const input = (c: TemplateContent, answers = c.sample.answers): PreviewInput => ({ content: c, answers, context: sampleContext(), assets: {} });

function find(blocks: Shown[], id: string): Shown | undefined {
  for (const b of blocks) {
    if (b.id === id) return b;
    const inner = b.kind === "section" ? b.blocks : b.kind === "columns" ? b.columns.flat() : [];
    const found = find(inner, id);
    if (found) return found;
  }
  return undefined;
}

const words = (doc: { content?: unknown[] } | null): string => JSON.stringify(doc).match(/"text":"([^"]*)"/g)?.map((t) => t.slice(8, -1)).join("") ?? "";

describe("the preview of the sample report", () => {
  const model = preview(input(content()));

  it("works out calculated values in order, and text with them", () => {
    expect(model.errors).toEqual([]);
    expect(model.values.severity).toBe("Critical");
    expect(model.values.deadline).toEqual(new Date("2026-10-24T01:14:00Z"));
    const cover = find(model.blocks, "b_cover");
    expect(cover).toMatchObject({
      title: "Security incident report",
      subtitle: "Fjordvik Logistik A/S",
      facts: [
        { label: "Report", value: "INC-2026-0142" },
        { label: "Detected", value: "21 October 2026, 03:14" },
        { label: "Severity", value: "Critical" },
      ],
    });
  });

  it("follows the rules: the callout's tone, the sections and blocks shown", () => {
    expect(find(model.blocks, "b_callout")).toMatchObject({ tone: "critical", title: "Critical severity" });
    expect(words((find(model.blocks, "b_callout") as { content: { content?: unknown[] } }).content))
      .toBe("Highest CVSS score 9.1. The incident notification is due by 24 October 2026, 03:14.");
    expect(find(model.blocks, "b_attack")).toBeDefined();
    // No photo of the evidence, so its image is left out.
    expect(find(model.blocks, "b_evidence")).toBeUndefined();
    expect(model.hidden).toContainEqual({ id: "b_evidence", reason: "Hidden by its rule" });
  });

  it("prints answers the way their questions say", () => {
    expect(find(model.blocks, "b_table")).toMatchObject({
      grid: {
        headers: ["Address", "Sign-in attempts", "Status"],
        rows: [["198.51.100.23", "1,204", "Blocked"], ["203.0.113.77", "611", "Blocked"], ["2001:db8::5", "27", "Monitored"]],
      },
    });
    expect(words((find(model.blocks, "b_credtext") as { content: { content?: unknown[] } }).content))
      .toBe("The portal admin password was changed to Hu••••••in. The full password was given to Mette Lund by phone.");
    expect((find(model.blocks, "b_srclist") as { items: unknown[] }).items).toHaveLength(2);
  });

  it("knows what the form requires", () => {
    expect(model.formRequired).toEqual(expect.arrayContaining(["q_summary", "q_detected", "q_cvss", "q_found", "q_attackers", "q_actions"]));
    expect(model.formHidden).toEqual([]);
  });

  it("falls onto pages by the page rules", () => {
    const { pages } = paginate(model.blocks);
    expect(pages[0].cover).toBe(true);
    expect(pages.map((p) => p.items[0].block.id)).toEqual(["b_cover", "b_summary", "b_attack", "b_actions", "b_signoff"]);
  });
});

describe("answers change what's printed", () => {
  it("leaves out a section whose rule says no, with what's in it", () => {
    const c = content();
    const model = preview(input(c, { ...c.sample.answers, q_found: false }));
    expect(find(model.blocks, "b_attack")).toBeUndefined();
    expect(find(model.blocks, "b_table")).toBeUndefined();
    expect(model.formHidden).toContain("q_attackers");
    expect(model.formRequired).not.toContain("q_attackers");
    expect(find(model.blocks, "b_callout")).toMatchObject({ tone: "critical" });
  });

  it("repeats a section for each item, with item inside it", () => {
    const c = content();
    c.layout.push({ id: "b_each", kind: "section", visible_when: null, title: "Address {{item.ip}}", intro: null, new_page: false,
      numbered: true, landscape: false, repeat_for: "answers.attackers", blocks: [
        { id: "b_eachtxt", kind: "heading", visible_when: "item.attempts > 100", text: "{{item.attempts}} attempts" },
      ] });
    const model = preview(input(c));
    const repeated = model.blocks.filter((b) => b.id.startsWith("b_each~"));
    expect(repeated.map((b) => b.kind === "section" && b.title)).toEqual(["Address 198.51.100.23", "Address 203.0.113.77", "Address 2001:db8::5"]);
    expect(repeated.map((b) => b.kind === "section" && b.blocks.length)).toEqual([1, 1, 0]);
    // What each repetition prints has an ID of its own, ending as its section's does.
    expect(repeated.flatMap((b) => (b.kind === "section" ? b.blocks.map((inner) => inner.id) : []))).toEqual(["b_eachtxt~0", "b_eachtxt~1"]);
  });

  it("gives everything printed an ID of its own, however sections repeat and nest", () => {
    const c = content();
    const heading = (id: string) => ({ id, kind: "heading" as const, visible_when: null, text: "{{item.ip}}" });
    const repeat = (id: string, blocks: TemplateContent["layout"]) => ({ id, kind: "section" as const, visible_when: null, title: "{{item.ip}}", intro: null, new_page: false,
      numbered: true, landscape: false, repeat_for: "answers.attackers", blocks });
    c.layout.push(repeat("b_outer", [heading("b_inhead"), { id: "b_incols", kind: "columns", visible_when: null, columns: [[heading("b_incol1")], [heading("b_incol2")]] },
      repeat("b_inner", [heading("b_deep")])]));
    const ids: string[] = [];
    const walk = (blocks: Shown[]) => blocks.forEach((b) => {
      ids.push(b.id);
      if (b.kind === "section") walk(b.blocks);
      if (b.kind === "columns") b.columns.forEach(walk);
    });
    const model = preview(input(c));
    walk(model.blocks);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain("b_deep~2~1");
    expect(paginate(model.blocks).pages.flatMap((p) => p.items.map((i) => i.block.id)).filter((id, i, list) => list.indexOf(id) !== i)).toEqual([]);
  });

  it("prints the first case of a switch with the value, else its otherwise", () => {
    const heading = (id: string, text: string) => ({ id, kind: "heading" as const, visible_when: null, text });
    const c = content();
    c.layout.push({ id: "b_switch", kind: "switch", visible_when: null, value: "answers.severity", cases: [
      { match: "High", blocks: [heading("b_high", "High")] },
      { match: "Critical", blocks: [heading("b_crit", "Act now"), heading("b_crit2", "{{answers.severity}}")] },
      { match: "Critical", blocks: [heading("b_again", "Never")] },
    ], otherwise: [heading("b_other", "Nothing to add")] });
    const printed = (model: ReturnType<typeof preview>) => ["b_high", "b_crit", "b_crit2", "b_again", "b_other"].filter((id) => find(model.blocks, id));

    const critical = preview(input(c));
    expect(critical.errors).toEqual([]);
    expect(printed(critical)).toEqual(["b_crit", "b_crit2"]);
    expect(find(critical.blocks, "b_crit2")).toMatchObject({ text: "Critical" });
    expect(critical.hidden).toContainEqual({ id: "b_high", reason: "The answers give “Critical”" });
    expect(critical.hidden).toContainEqual({ id: "b_other", reason: "The answers give “Critical”" });

    const low = preview(input(c, { ...c.sample.answers, q_cvss: 2 }));
    expect(low.values.severity).toBe("Low");
    expect(printed(low)).toEqual(["b_other"]);
  });

  it("says which expressions failed, and carries on", () => {
    const c = content();
    c.layout.push({ id: "b_broken", kind: "heading", visible_when: null, text: "{{ date(\"not a date\") }} and on" });
    const model = preview(input(c));
    expect(find(model.blocks, "b_broken")).toMatchObject({ text: "⚠ and on" });
    expect(model.errors.map((e) => e.element)).toEqual(["b_broken"]);
  });
});

describe("a table's rows, numbered", () => {
  it("puts a No. column first, the same in every table of those rows", () => {
    const c = content();
    c.layout.push(
      { id: "b_rows1", kind: "table", visible_when: null, question: "q_attackers", caption: "", columns: ["ip"], empty_text: "", row_numbers: true },
      { id: "b_rows2", kind: "table", visible_when: null, question: "q_attackers", caption: "", columns: ["status"], empty_text: "", row_numbers: true },
    );
    const model = preview(input(c));
    expect(find(model.blocks, "b_rows1")).toMatchObject({ grid: { headers: ["No.", "Address"], rows: [["1", "198.51.100.23"], ["2", "203.0.113.77"], ["3", "2001:db8::5"]] } });
    expect(find(model.blocks, "b_rows2")).toMatchObject({ grid: { headers: ["No.", "Status"], rows: [["1", "Blocked"], ["2", "Blocked"], ["3", "Monitored"]] } });
    // Not asked for: as before.
    expect((find(model.blocks, "b_table") as { grid: { headers: string[] } }).grid.headers).toEqual(["Address", "Sign-in attempts", "Status"]);
    c.settings.language = "da";
    expect((find(preview(input(c)).blocks, "b_rows1") as { grid: { headers: string[] } }).grid.headers[0]).toBe("Nr.");
  });
});

describe("a person picked from the company", () => {
  it("offers the sample report's people by what the question asks for, and prints who's picked", () => {
    const c = content();
    const people = samplePeople(sampleContext());
    expect(people.map((p) => [p.id, p.role, p.display_name])).toEqual([["sample-author", "technician", "Freja Holm"], ["sample-reviewer", "reviewer", "Anders Berg"]]);
    const question = { ...c.form[0].questions[0], id: "q_done1", key: "done_by", type: "person", label: "Procedure performed by", required: false, settings: { who: "technicians" } };
    expect(peopleFor(question, people).map((p) => p.display_name)).toEqual(["Freja Holm"]);
    expect(peopleFor({ ...question, settings: { who: "everyone" } }, people)).toHaveLength(2);

    c.form[0].questions.push(question);
    c.layout.push(
      { id: "b_done", kind: "answer", visible_when: null, question: "q_done1", show_label: true },
      { id: "b_donetext", kind: "heading", visible_when: null, text: '{{answers.done_by.filled ? answers.done_by.display_name + ", " + answers.done_by.job_title : "Nobody yet"}}' },
    );
    const before = preview(input(c));
    expect(before.errors).toEqual([]);
    expect(find(before.blocks, "b_donetext")).toMatchObject({ text: "Nobody yet" });
    const after = preview(input(c, { ...c.sample.answers, q_done1: people[0] }));
    expect(find(after.blocks, "b_done")).toMatchObject({ label: "Procedure performed by", text: "Freja Holm" });
    expect(find(after.blocks, "b_donetext")).toMatchObject({ text: `Freja Holm, ${people[0].job_title}` });
  });
});

describe("signature pads", () => {
  it("draws a pad's strokes where it signs, and says so where it isn't signed", () => {
    const c = content();
    c.form[0].questions.push({ ...c.form[0].questions[0], id: "q_pad1", key: "witness", type: "signature", label: "Witness", required: false, settings: {} });
    c.layout.push(
      { id: "b_pads", kind: "signatures", visible_when: null, layout: "row", show_date: true,
        signers: [{ role: "pad", label: "Witness", style: "handwritten", question: "q_pad1" }, { role: "technician", label: "Technician", style: "handwritten" }] },
      { id: "b_padanswer", kind: "answer", visible_when: null, question: "q_pad1", show_label: true },
      { id: "b_padtext", kind: "heading", visible_when: null, text: '{{answers.witness.filled ? "Signed" : "Not yet"}}' },
    );
    const empty = preview(input(c));
    expect(find(empty.blocks, "b_pads")).toMatchObject({ signers: [{ role: "pad", strokes: null }, { role: "technician" }] });
    expect(find(empty.blocks, "b_padanswer")).toMatchObject({ text: "Not signed" });
    expect(find(empty.blocks, "b_padtext")).toMatchObject({ text: "Not yet" });

    const strokes = [[10, 20, 30, 40], [50, 60]];
    const signed = preview(input(c, { ...c.sample.answers, q_pad1: { strokes } }));
    expect(find(signed.blocks, "b_pads")).toMatchObject({ signers: [{ role: "pad", strokes }, { role: "technician" }] });
    expect(find(signed.blocks, "b_padanswer")).toMatchObject({ text: null, strokes });
    expect(find(signed.blocks, "b_padtext")).toMatchObject({ text: "Signed" });
  });
});

describe("what questions start as", () => {
  const started = "2026-11-20T13:47:31Z";
  const withDefaults = () => {
    const c = content();
    const q = (id: string, key: string, type: string, rule: string, settings: Record<string, unknown> = {}) =>
      ({ ...c.form[0].questions[0], id, key, type, label: key, required: false, default: rule, settings });
    c.form[0].questions.push(
      q("q_day1", "day", "datetime", "report.started", { mode: "date" }),
      q("q_when", "moment", "datetime", "report.started", { mode: "datetime" }),
      q("q_who1", "who", "text", "author.display_name"),
    );
    c.layout.push({ id: "b_start", kind: "heading", visible_when: null, text: "{{answers.day}} / {{answers.moment}} / {{answers.who}}" });
    return c;
  };
  const run = (c: TemplateContent, answers: Record<string, unknown>) => {
    const context = sampleContext();
    context.report.started = started;
    return preview({ content: c, answers, context, assets: {}, timezone: "Europe/Copenhagen" });
  };

  it("gives a question not answered yet its start: a date question the day, a date and time question the minute", () => {
    const c = withDefaults();
    const model = run(c, c.sample.answers);
    expect(model.errors).toEqual([]);
    expect(model.defaults).toEqual({ q_day1: "2026-11-19T23:00:00.000Z", q_when: "2026-11-20T13:47:00.000Z", q_who1: "Freja Holm" });
    expect(find(model.blocks, "b_start")).toMatchObject({ text: "20 November 2026 / 20 November 2026, 14:47 / Freja Holm" });
  });

  it("leaves answered questions, and ones cleared on purpose, as they are", () => {
    const c = withDefaults();
    const model = run(c, { ...c.sample.answers, q_day1: "2026-10-01T22:00:00.000Z", q_who1: null });
    expect(model.defaults).toEqual({ q_when: "2026-11-20T13:47:00.000Z" });
    expect(model.values.who).toBeNull();
  });
});

describe("printValue", () => {
  const engine = new Engine({ "project.start_date": "timestamp", "project.end_date": "timestamp" }, {});
  const values = { project: { start_date: "2026-11-01T00:00:00+01:00", end_date: "2026-11-20T00:00:00+01:00" } };
  const print = (expr: string, language = "en") => printValue(engine.evaluate(expr, values), language, "Europe/Copenhagen");

  it("prints a length of time in words", () => {
    expect(print('duration("72h")')).toBe("3 days");
    expect(print('duration("72h")', "da")).toBe("3 dage");
    expect(print('duration("90m") + duration("1.5s")')).toBe("1 hour 30 minutes 1.5 seconds");
    expect(print('duration("90m") + duration("1.5s")', "da")).toBe("1 time 30 minutter 1,5 sekunder");
    expect(print("project.end_date - project.start_date")).toBe("19 days");
    expect(print("project.start_date - project.end_date")).toBe("-19 days");
    expect(print('duration("0s")')).toBe("0 minutes");
  });

  it("prints a moment at midnight as a date alone", () => {
    expect(print("project.start_date")).toBe("1 November 2026");
    expect(print('project.start_date + duration("9h")')).toBe("1 November 2026, 09:00");
    expect(print("project.start_date", "da")).toBe("1 november 2026");
  });
});
