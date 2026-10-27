// Block kinds for the Layout tab: each one's label, what it's for, and what a new one
// starts with (the server's defaults, backend/app/templates/content.py). Everything a
// block holds is printed in the PDF.

import BookOpenText from "@lucide/svelte/icons/book-open-text";
import ChartColumnBig from "@lucide/svelte/icons/chart-column-big";
import Columns2 from "@lucide/svelte/icons/columns-2";
import Heading2 from "@lucide/svelte/icons/heading-2";
import ImageIcon from "@lucide/svelte/icons/image";
import Images from "@lucide/svelte/icons/images";
import LibraryBig from "@lucide/svelte/icons/library-big";
import ListTree from "@lucide/svelte/icons/list-tree";
import MessageSquareText from "@lucide/svelte/icons/message-square-text";
import MessageSquareWarning from "@lucide/svelte/icons/message-square-warning";
import PenTool from "@lucide/svelte/icons/pen-tool";
import Pilcrow from "@lucide/svelte/icons/pilcrow";
import SeparatorHorizontal from "@lucide/svelte/icons/separator-horizontal";
import SquareSplitVertical from "@lucide/svelte/icons/square-split-vertical";
import Table2 from "@lucide/svelte/icons/table-2";
import { newId } from "./edit";
import type { Icon } from "./fieldIcons";
import type { Block, BlockKind, RichText } from "./types";

export interface BlockType {
  label: string;
  hint: string;
  group: "Structure" | "Text" | "Answers" | "Pictures" | "Sign-off";
  icon: Icon;
}

export const BLOCK_TYPES: Record<BlockKind, BlockType> = {
  section: { label: "Section", hint: "A numbered part of the report", group: "Structure", icon: SquareSplitVertical },
  cover: { label: "Cover", hint: "The first page: title and key facts", group: "Structure", icon: BookOpenText },
  toc: { label: "Contents", hint: "The sections, with their pages", group: "Structure", icon: ListTree },
  columns: { label: "Columns", hint: "Blocks side by side", group: "Structure", icon: Columns2 },
  page_break: { label: "Page break", hint: "Starts a new page", group: "Structure", icon: SeparatorHorizontal },
  heading: { label: "Heading", hint: "A sub-heading", group: "Text", icon: Heading2 },
  text: { label: "Text", hint: "Paragraphs with answers and names", group: "Text", icon: Pilcrow },
  callout: { label: "Callout", hint: "A coloured note", group: "Text", icon: MessageSquareWarning },
  sources: { label: "Sources", hint: "References, numbered", group: "Text", icon: LibraryBig },
  answer: { label: "Answer", hint: "One answer, with its question", group: "Answers", icon: MessageSquareText },
  table: { label: "Table", hint: "The rows of a repeating group", group: "Answers", icon: Table2 },
  severity_summary: { label: "Severity summary", hint: "How many rows of each severity", group: "Answers", icon: ChartColumnBig },
  image: { label: "Image", hint: "A picture or a photo", group: "Pictures", icon: ImageIcon },
  gallery: { label: "Photo gallery", hint: "Several photos in a grid", group: "Pictures", icon: Images },
  signatures: { label: "Signatures", hint: "Sign-off boxes", group: "Sign-off", icon: PenTool },
};

export const BLOCK_GROUPS = ["Structure", "Text", "Answers", "Pictures", "Sign-off"] as const;

export const emptyDoc = (text = ""): RichText => ({
  type: "doc",
  content: [{ type: "paragraph", content: text ? [{ type: "text", text }] : [] }],
});

/** A new block of a kind, with the server's defaults. A section inside another doesn't start a page. */
export function newBlock(kind: BlockKind, nested = false): Block {
  const base = { id: newId("b"), visible_when: null };
  switch (kind) {
    case "section":
      return { ...base, kind, title: "New section", intro: null, new_page: !nested, numbered: true, landscape: false, repeat_for: null, blocks: [] };
    case "cover":
      return { ...base, kind, title: "{{report.title}}", subtitle: "{{customer.name}}", facts: [{ label: "Report", value: "{{report.number}}" }], show_logo: true };
    case "toc":
      return { ...base, kind, title: "Contents", depth: 1 };
    case "heading":
      return { ...base, kind, text: "New heading" };
    case "text":
      return { ...base, kind, content: emptyDoc("Write here. Insert answers and names with the button above.") };
    case "answer":
      return { ...base, kind, question: null, show_label: true };
    case "table":
      return { ...base, kind, question: null, caption: "", columns: null, empty_text: "No rows." };
    case "image":
      return { ...base, kind, source: "template", asset: null, question: null, caption: "", width: "full" };
    case "gallery":
      return { ...base, kind, question: null, caption: "", per_row: 2 };
    case "callout":
      return { ...base, kind, tone: "info", tone_rule: null, colour: null, title: "", content: emptyDoc("A note for the reader.") };
    case "severity_summary":
      return { ...base, kind, question: null, column: null, levels: ["Critical", "High", "Medium", "Low"], caption: "" };
    case "sources":
      return { ...base, kind, intro: "", items: [], question: null };
    case "signatures":
      return { ...base, kind, signers: [{ role: "technician", label: "Technician", style: "handwritten" }], layout: "row", show_date: true };
    case "columns":
      return { ...base, kind, columns: [[], []] };
    case "page_break":
      return { ...base, kind };
  }
}

/** A short description of a block, for its card. */
export function blockSummary(block: Block): string {
  switch (block.kind) {
    case "section":
      return block.title;
    case "heading":
      return block.text;
    case "cover":
    case "toc":
      return block.title;
    case "callout":
      return block.title || `${block.tone[0].toUpperCase()}${block.tone.slice(1)} callout`;
    case "table":
    case "image":
    case "gallery":
    case "severity_summary":
      return block.caption || BLOCK_TYPES[block.kind].label;
    default:
      return BLOCK_TYPES[block.kind].label;
  }
}
