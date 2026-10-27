import { describe, expect, it } from "vitest";
import incident from "../../../../shared/templates/incident.json";
import { paginate } from "./pages";
import { preview, sampleContext, type PreviewInput, type Shown } from "./preview";
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
  });

  it("says which expressions failed, and carries on", () => {
    const c = content();
    c.layout.push({ id: "b_broken", kind: "heading", visible_when: null, text: "{{ date(\"not a date\") }} and on" });
    const model = preview(input(c));
    expect(find(model.blocks, "b_broken")).toMatchObject({ text: "⚠ and on" });
    expect(model.errors.map((e) => e.element)).toEqual(["b_broken"]);
  });
});
