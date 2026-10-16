import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

const DISPLAY_MATH = /\\\[([\s\S]+?)\\\]/g;
const INLINE_MATH = /\\\(([\s\S]+?)\\\)/g;

/**
 * The model writes LaTeX with \[...\] and \(...\) delimiters, while remark-math
 * expects $$...$$. Normalize the delimiters before parsing. Single-dollar math
 * stays disabled so currency amounts like "$215 billion" never turn into math.
 */
function normalizeMath(source) {
  if (typeof source !== "string") return source;
  return source
    .replace(DISPLAY_MATH, (_, body) => `\n\n$$\n${body.trim()}\n$$\n\n`)
    .replace(INLINE_MATH, (_, body) => `$$${body.trim()}$$`);
}

const COMPONENTS = {
  h1: ({ children }) => <h1 className="mb-4 mt-2 text-xl font-bold text-white sm:text-2xl">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-3 mt-7 text-lg font-semibold text-white">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 mt-6 text-base font-semibold text-slate-100">{children}</h3>,
  p: ({ children }) => <p className="mb-4 leading-7 text-slate-300 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
  em: ({ children }) => <em className="text-slate-300 italic">{children}</em>,
  ul: ({ children }) => <ul className="mb-4 list-disc space-y-1.5 pl-5 text-slate-300">{children}</ul>,
  ol: ({ children }) => <ol className="mb-4 list-decimal space-y-1.5 pl-5 text-slate-300">{children}</ol>,
  li: ({ children }) => <li className="leading-7 marker:text-indigo-400/70">{children}</li>,
  hr: () => <hr className="my-6 border-white/[0.08]" />,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-indigo-400 underline decoration-indigo-400/40 hover:text-indigo-300">
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-4 border-l-2 border-indigo-400/50 pl-4 text-slate-400 italic">{children}</blockquote>
  ),
  table: ({ children }) => (
    <div className="mb-5 w-full overflow-x-auto rounded-xl border border-white/[0.08]">
      <table className="w-full min-w-[560px] border-collapse text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-white/[0.04] text-slate-200">{children}</thead>,
  tbody: ({ children }) => <tbody className="divide-y divide-white/[0.06]">{children}</tbody>,
  tr: ({ children }) => <tr className="transition hover:bg-white/[0.03]">{children}</tr>,
  th: ({ children }) => (
    <th className="whitespace-nowrap border-r border-white/[0.06] px-3.5 py-2.5 text-left text-xs font-semibold uppercase tracking-wide last:border-r-0">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="whitespace-nowrap border-r border-white/[0.04] px-3.5 py-2.5 text-slate-300 last:border-r-0">
      {children}
    </td>
  ),
  pre: ({ children }) => (
    <pre className="mb-5 overflow-x-auto rounded-xl border border-white/[0.08] bg-ink-950/80 p-4 text-[13px] leading-6">
      {children}
    </pre>
  ),
  code: ({ children, className, ...props }) => {
    const block = typeof className === "string" && className.startsWith("language-");
    return (
      <code
        className={
          block
            ? "font-mono text-[13px] text-slate-200"
            : "rounded-md border border-white/[0.08] bg-white/[0.06] px-1.5 py-0.5 text-[13px] text-indigo-300"
        }
        {...props}
      >
        {children}
      </code>
    );
  },
};

export default function Markdown({ children }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, [remarkMath, { singleDollarTextMath: false }]]}
      rehypePlugins={[rehypeKatex]}
      components={COMPONENTS}
    >
      {normalizeMath(children)}
    </ReactMarkdown>
  );
}
