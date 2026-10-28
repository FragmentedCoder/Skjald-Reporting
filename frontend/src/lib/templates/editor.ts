// The rich text editor's setup (TipTap): only what Skjald prints, so what it makes is
// exactly what the server accepts (backend/app/templates/text.py): paragraphs, two
// heading levels, lists, line breaks, bold, italic, underline, strike-through, code,
// links with nothing but their address, and variables, which print an expression's
// value. TipTap's own stylesheet isn't injected (the CSP allows no inline styles);
// the component carries the few rules the editor needs.

import { Editor, Node, type Extensions, type JSONContent } from "@tiptap/core";
import Link from "@tiptap/extension-link";
import StarterKit from "@tiptap/starter-kit";

export const Variable = Node.create({
  name: "variable",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,
  addAttributes() {
    return { expr: { default: "" } };
  },
  parseHTML() {
    return [{ tag: "span[data-variable]", getAttrs: (element) => ({ expr: (element as HTMLElement).dataset.variable ?? "" }) }];
  },
  renderHTML({ node }) {
    return ["span", { "data-variable": node.attrs.expr, class: "variable" }, `{{ ${node.attrs.expr} }}`];
  },
  renderText({ node }) {
    return `{{${node.attrs.expr}}}`;
  },
});

/** A link with its address only: no target, rel or class attributes to refuse. */
const AddressLink = Link.extend({
  addAttributes() {
    return { href: { default: null } };
  },
}).configure({ openOnClick: false, autolink: false, protocols: ["https", "http", "mailto"], defaultProtocol: "https" });

export const EXTENSIONS: Extensions = [
  StarterKit.configure({
    blockquote: false,
    codeBlock: false,
    horizontalRule: false,
    link: false,
    heading: { levels: [3, 4] },
  }),
  AddressLink,
  Variable,
];

/** onKey sees each key first, and returns true for one it handled (such as choosing a suggested name). */
export function makeEditor(element: HTMLElement, content: JSONContent, label: string, onUpdate: (doc: JSONContent) => void,
  onKey: (event: KeyboardEvent) => boolean = () => false): Editor {
  return new Editor({
    element,
    extensions: EXTENSIONS,
    content,
    injectCSS: false,
    editorProps: {
      attributes: { "aria-label": label, role: "textbox", "aria-multiline": "true", class: "rich-input" },
      handleKeyDown: (_view, event) => onKey(event),
    },
    onUpdate: ({ editor }) => onUpdate(editor.getJSON()),
  });
}
