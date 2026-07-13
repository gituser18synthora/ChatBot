import { memo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import { Icon } from "@/components/ui/Icons";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github.css";

/**
 * Rich renderer for assistant messages: GitHub-flavored Markdown (tables,
 * strikethrough, task lists), math ($…$ / $$…$$ via KaTeX), syntax-highlighted
 * code blocks with a copy button, and inline HTML — sanitized.
 *
 * Pipeline order matters: rehype-raw parses any inline HTML the LLM produced,
 * rehype-sanitize immediately strips anything unsafe (scripts, event handlers,
 * javascript: URLs), and only then do KaTeX/highlight run so their generated
 * markup is not sanitized away.
 */
const schema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    // remark-math emits <code class="language-math math-inline|math-display">;
    // the default schema only keeps class names matching /^language-./ on code.
    code: [["className", /^language-./, "math-inline", "math-display"]],
  },
} as typeof defaultSchema;

function CodeBlock({ children, ...props }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);

  const extractText = (node: ReactNode): string => {
    if (node == null || typeof node === "boolean") return "";
    if (typeof node === "string" || typeof node === "number") return String(node);
    if (Array.isArray(node)) return node.map(extractText).join("");
    if (typeof node === "object" && "props" in node) return extractText((node as any).props?.children);
    return "";
  };

  const copy = async () => {
    await navigator.clipboard.writeText(extractText(children).replace(/\n$/, ""));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="group/code relative">
      <button
        type="button"
        onClick={copy}
        aria-label="Copy code"
        className="absolute right-2 top-2 z-10 inline-flex items-center gap-1 rounded-md bg-slate-700/80 px-2 py-1 text-[11px] font-medium text-slate-200 opacity-0 transition hover:bg-slate-600 group-hover/code:opacity-100"
      >
        {copied ? <Icon.Check width={12} height={12} /> : <Icon.Copy width={12} height={12} />}
        {copied ? "Copied" : "Copy"}
      </button>
      <pre {...props}>{children}</pre>
    </div>
  );
}

export const Markdown = memo(function Markdown({ children }: { children: string }) {
  return (
    <div
      className={
        // Typography plugin does the heavy lifting; the prose-* overrides keep
        // the scale compact for chat bubbles and make embedded blocks scroll
        // instead of overflowing the bubble.
        "prose prose-sm prose-slate max-w-none break-words " +
        "prose-headings:font-semibold prose-headings:text-slate-900 " +
        "prose-h1:text-lg prose-h2:text-base prose-h3:text-sm " +
        "prose-p:leading-relaxed prose-li:my-0.5 " +
        "prose-a:text-brand-600 prose-a:font-medium hover:prose-a:text-brand-700 " +
        "prose-blockquote:border-l-brand-300 prose-blockquote:text-slate-600 prose-blockquote:not-italic " +
        "prose-code:rounded prose-code:bg-slate-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:text-[0.85em] prose-code:font-normal prose-code:text-rose-600 prose-code:before:content-none prose-code:after:content-none " +
        "prose-pre:my-3 prose-pre:rounded-xl prose-pre:border prose-pre:border-slate-200 prose-pre:bg-slate-50 prose-pre:p-3.5 prose-pre:text-[13px] prose-pre:leading-relaxed " +
        "[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-inherit " +
        "prose-table:my-3 prose-th:bg-slate-50 prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2 prose-tr:border-slate-200 " +
        "prose-hr:my-4 prose-img:rounded-lg " +
        "[&_.katex-display]:overflow-x-auto [&_.katex-display]:py-1"
      }
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, schema], rehypeKatex, rehypeHighlight]}
        components={{
          // Tables scroll inside the bubble instead of blowing out the layout.
          table: ({ node: _n, ...props }) => (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table {...props} className="!my-0" />
            </div>
          ),
          a: ({ node: _n, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
          pre: ({ node: _n, ...props }) => <CodeBlock {...props} />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
});
