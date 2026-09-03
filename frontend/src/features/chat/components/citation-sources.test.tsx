import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CitationSources } from "@/features/chat/components/citation-sources";
import type { RetrievedSource } from "@/types/api";

const sources: RetrievedSource[] = [
  {
    id: 101,
    page_number: 4,
    chunk_index: 12,
    distance: 0.08,
  },
  {
    id: 102,
    page_number: 7,
    chunk_index: 18,
    distance: 0.2,
  },
];

describe("CitationSources", () => {
  it("renders nothing when sources are undefined", () => {
    const { container } = render(<CitationSources />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when sources are empty", () => {
    const { container } = render(<CitationSources sources={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("is collapsed by default", () => {
    render(<CitationSources sources={sources} />);

    const toggle = screen.getByRole("button", {
      name: /2 sources/i,
    });

    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    const controlledId = toggle.getAttribute("aria-controls");
    const content = document.getElementById(controlledId ?? "");
    expect(content?.hasAttribute("hidden")).toBe(true);
  });

  it("expands when the source button is clicked", () => {
    render(<CitationSources sources={sources} />);

    const toggle = screen.getByRole("button", {
      name: /2 sources/i,
    });

    fireEvent.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Source 1")).toBeDefined();
    expect(screen.getByText("Source 2")).toBeDefined();
  });

  it("collapses again when the source button is clicked", () => {
    render(<CitationSources sources={sources} />);

    const toggle = screen.getByRole("button", {
      name: /2 sources/i,
    });

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("formats page and chunk metadata", () => {
    render(<CitationSources sources={sources} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /2 sources/i,
      }),
    );

    expect(screen.getByText("Page 4")).toBeDefined();
    expect(screen.getByText("Chunk 12")).toBeDefined();
    expect(screen.getByText("Page 7")).toBeDefined();
    expect(screen.getByText("Chunk 18")).toBeDefined();
  });

  it("formats relevance from the distance value", () => {
    render(<CitationSources sources={sources} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /2 sources/i,
      }),
    );

    expect(screen.getByText("Relevance 92%")).toBeDefined();
    expect(screen.getByText("Relevance 80%")).toBeDefined();
  });

  it("handles missing page and chunk metadata", () => {
    const source: RetrievedSource = {
      id: 103,
      page_number: null,
      chunk_index: null,
      distance: 0.15,
    };

    render(<CitationSources sources={[source]} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    );

    expect(screen.getByText("Page unavailable")).toBeDefined();
    expect(screen.getByText("Chunk unavailable")).toBeDefined();
    expect(screen.getByText("Relevance 85%")).toBeDefined();
  });

  it("uses the singular source label for one source", () => {
    render(
      <CitationSources
        sources={[
          {
            id: 104,
            page_number: 2,
            chunk_index: 5,
            distance: 0.05,
          },
        ]}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    ).toBeDefined();
  });

  it("clamps invalid relevance values safely", () => {
    render(
      <CitationSources
        sources={[
          {
            id: 105,
            page_number: 1,
            chunk_index: 1,
            distance: 2,
          },
          {
            id: 106,
            page_number: 2,
            chunk_index: 2,
            distance: -1,
          },
        ]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /2 sources/i,
      }),
    );

    expect(screen.getByText("Relevance 0%")).toBeDefined();
    expect(screen.getByText("Relevance 100%")).toBeDefined();
  });

  it("renders an unavailable relevance value for non-finite distance", () => {
    render(
      <CitationSources
        sources={[
          {
            id: 107,
            page_number: 3,
            chunk_index: 4,
            distance: Number.NaN,
          },
        ]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    );

    expect(screen.getByText("Relevance —")).toBeDefined();
  });
});
