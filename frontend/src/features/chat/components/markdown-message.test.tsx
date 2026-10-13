import "@testing-library/jest-dom/vitest";

import { act, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { MarkdownMessage } from "./markdown-message";

describe("MarkdownMessage", () => {
  it("renders GFM tables, bold text, headings, and lists", () => {
    const tableContent = [
      "# Project status",
      "",
      "**Completed:** Slice 1",
      "",
      "- Backend memory",
      "- Retrieval context",
      "",
      "| Feature | Status |",
      "| --- | --- |",
      "| Memory | Ready |",
      "| RAG | Ready |",
    ].join("\n");

    render(<MarkdownMessage content={tableContent} />);

    expect(
      screen.getByRole("heading", {
        name: "Project status",
        level: 1,
      }),
    ).toBeInTheDocument();

    expect(screen.getByText("Completed:")).toBeInTheDocument();
    expect(screen.getByText("Slice 1")).toBeInTheDocument();

    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getByText("Backend memory")).toBeInTheDocument();
    expect(screen.getByText("Retrieval context")).toBeInTheDocument();

    expect(screen.getByRole("table")).toBeInTheDocument();

    expect(screen.getByText("Feature")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getAllByText("Ready")).toHaveLength(2);
  });

  it("renders fenced code blocks and preserves language attributes", () => {
    const codeContent = [
      "```typescript",
      'const answer: string = "ready";',
      "```",
    ].join("\n");

    render(<MarkdownMessage content={codeContent} />);

    const code = screen.getByText('const answer: string = "ready";');

    expect(code.tagName).toBe("CODE");
    expect(code).toHaveAttribute("data-language", "typescript");
    expect(code).toHaveClass("font-mono");
  });

  it("gracefully renders an incomplete fenced code block while streaming", () => {
    const incompleteCode = [
      "Here is the implementation:",
      "",
      "```typescript",
      'const answer = await fetch("/api/chat");',
    ].join("\n");

    render(<MarkdownMessage content={incompleteCode} isStreaming/>);

    expect(
      screen.getByText((content) =>
        content.includes('const answer = await fetch("/api/chat");')
      ),
    ).toBeInTheDocument();

    expect(screen.getByText("Here is the implementation:")).toBeInTheDocument();
  });

  it("gracefully renders incomplete GFM table syntax", () => {
    const incompleteTable = [
      "| Feature | Status |",
      "| --- |",
      "| Memory |",
    ].join("\n");

    render(<MarkdownMessage content={incompleteTable} isStreaming/>);

    expect(screen.getByText((c) => c.includes("Feature"))).toBeInTheDocument();
    expect(screen.getByText((c) => c.includes("Status"))).toBeInTheDocument();
    expect(screen.getByText((c) => c.includes("Memory"))).toBeInTheDocument();
  });

  it("does not execute or render raw script HTML", () => {
    const payload = [
      "Safe text",
      "",
      '<script>alert("xss")</script>',
      "",
      '<img src="x" onerror="alert(\'xss\')" />',
    ].join("\n");

    render(<MarkdownMessage content={payload}/>);

    expect(screen.getByText("Safe text")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(document.querySelector("script")).not.toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain("<script>");
    expect(document.body.innerHTML).not.toContain("onerror=");
  });

  it("does not allow javascript links through sanitized markdown", () => {
    const payload = '[malicious](javascript:alert("xss"))';

    render(<MarkdownMessage content={payload}/>);

    const link = screen.getByText("malicious");

    expect(link).toBeInTheDocument();

    if (link instanceof HTMLAnchorElement) {
      const href = link.getAttribute("href");
      if (href) {
        expect(href).not.toMatch(/^javascript:/i);
      } else {
        expect(href).toBeNull();
      }
    }
  });

  it("handles progressive streaming updates without act warnings", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    function StreamingHarness() {
      const [content, setContent] = useState("The");

      return (
        <div>
          <button
            type="button"
            onClick={() =>
              setContent(
                "The answer is **ready**.\n\n```ts\nconst ok = true;\n```",
              )
            }
          >
            Continue
          </button>

          <MarkdownMessage content={content} isStreaming />
        </div>
      );
    }

    render(<StreamingHarness />);

    expect(screen.getByText("The")).toBeInTheDocument();

    await act(async () => {
      screen.getByRole("button", { name: "Continue" }).click();
    });

    await waitFor(() => {
      expect(
        screen.getByText((t) => t.includes("The answer is")),
      ).toBeInTheDocument();
      expect(screen.getByText("ready")).toBeInTheDocument();
      expect(screen.getByText("const ok = true;")).toBeInTheDocument();
    });

    const actWarnings = consoleError.mock.calls.filter(([message]) =>
      String(message).includes("not wrapped in act"),
    );

    expect(actWarnings).toHaveLength(0);

    consoleError.mockRestore();
  });
});
