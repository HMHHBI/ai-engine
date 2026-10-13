"use client";

import { useDeferredValue } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

interface MarkdownMessageProps {
  content: string;
  isStreaming?: boolean;
  className?: string;
}

function closeIncompleteCodeFence(markdown: string): string {
  const fenceMatches = markdown.match(/^ {0,3}(`{3,}|~{3,})/gm) ?? [];

  let openFence: string | null = null;

  for (const match of fenceMatches) {
    const fence = match.trim();

    if (!openFence) {
      openFence = fence;
      continue;
    }

    const openingChar = openFence[0];
    const closingChar = fence[0];

    if (
      openingChar === closingChar &&
      fence.length >= openFence.length
    ) {
      openFence = null;
    }
  }

  if (!openFence) {
    return markdown;
  }

  const fenceChar = openFence[0];
  const fenceLength = openFence.length;

  return `${markdown}\n\n${fenceChar.repeat(fenceLength)}`;
}

function CodeBlock({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  const languageMatch =
    typeof className === "string"
      ? className.match(/(?:^|\s)language-([^\s]+)/)
      : null;

  const language = languageMatch?.[1];

  return (
    <code
      className={cn(
        "font-mono text-[0.8125rem] leading-6",
        "text-zinc-100",
        className,
      )}
      data-language={language}
      {...props}
    >
      {children}
    </code>
  );
}

export function MarkdownMessage({
  content,
  isStreaming = false,
  className,
}: MarkdownMessageProps) {
  const deferredContent = useDeferredValue(content);

  const markdown = isStreaming
    ? closeIncompleteCodeFence(deferredContent)
    : deferredContent;

  return (
    <div
      className={cn(
        "min-w-0 max-w-none break-words",
        "text-xs leading-5 sm:text-sm sm:leading-6",
        "[&_a]:font-medium [&_a]:text-zinc-100 [&_a]:underline [&_a]:underline-offset-2",
        "[&_a:hover]:text-white",
        "[&_blockquote]:my-3 [&_blockquote]:border-l-2 [&_blockquote]:border-zinc-600 [&_blockquote]:pl-4 [&_blockquote]:text-zinc-300",
        "[&_code]:rounded [&_code]:bg-zinc-800/80 [&_code]:px-1 [&_code]:py-0.5",
        "[&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-zinc-700",
        "[&_pre]:bg-zinc-950 [&_pre]:p-3 sm:[&_pre]:p-4",
        "[&_pre_code]:block [&_pre_code]:bg-transparent [&_pre_code]:p-0",
        "[&_h1]:mb-3 [&_h1]:mt-5 [&_h1]:text-lg [&_h1]:font-semibold [&_h1]:leading-tight",
        "[&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:leading-tight",
        "[&_h3]:mb-2 [&_h3]:mt-4 [&_h3]:text-sm [&_h3]:font-semibold",
        "[&_h1:first-child]:mt-0 [&_h2:first-child]:mt-0 [&_h3:first-child]:mt-0",
        "[&_p]:my-2",
        "[&_p:first-child]:mt-0 [&_p:last-child]:mb-0",
        "[&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5",
        "[&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5",
        "[&_li]:my-1",
        "[&_li>p]:my-0",
        "[&_hr]:my-4 [&_hr]:border-zinc-700",
        "[&_table]:my-3 [&_table]:w-full [&_table]:border-collapse",
        "[&_thead]:bg-zinc-800/80",
        "[&_th]:border [&_th]:border-zinc-700 [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold",
        "[&_td]:border [&_td]:border-zinc-700 [&_td]:px-3 [&_td]:py-2",
        "[&_tr]:align-top",
        "[&_strong]:font-semibold [&_strong]:text-white",
        "[&_em]:text-zinc-200",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          code: CodeBlock,
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
