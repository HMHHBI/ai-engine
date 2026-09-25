import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CitationSources } from "@/features/chat/components/citation-sources";
import type { RetrievedSource } from "@/types/api";

vi.mock("@/features/documents/document-store", () => ({
  useDocumentStore: (selector: (state: unknown) => unknown) =>
    selector({
      documentsByChat: {
        1: [
          {
            id: 101,
            chat_id: 1,
            filename: "Attention Is All You Need.pdf",
          },
          {
            id: 102,
            chat_id: 1,
            filename: "Research Methods.pdf",
          },
        ],
      },
    }),
}));

const sources: RetrievedSource[] = [
  {
    id: 101,
    document_id: 101,
    page_number: 4,
    chunk_index: 12,
    distance: 0.08,
    snippet: "The model achieves strong results on translation tasks.",
  },
  {
    id: 102,
    document_id: 102,
    page_number: 7,
    chunk_index: 18,
    distance: 0.2,
    snippet: "The evaluation compares several established baselines.",
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

    expect(toggle).toHaveAttribute("aria-expanded", "false");

    const controlledId = toggle.getAttribute("aria-controls");
    const content = document.getElementById(controlledId ?? "");

    expect(content).toHaveAttribute("hidden");
  });

  it("renders the genuine retrieved snippets as quotations", () => {
    render(<CitationSources sources={sources} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /2 sources/i,
      }),
    );

    expect(
      screen.getAllByTestId("citation-snippet")[0],
    ).toHaveTextContent(
      "“The model achieves strong results on translation tasks.”",
    );

    expect(
      screen.getAllByTestId("citation-snippet")[1],
    ).toHaveTextContent(
      "“The evaluation compares several established baselines.”",
    );
  });

  it("renders a truthful fallback when snippet is absent", () => {
    render(
      <CitationSources
        sources={[
          {
            id: 103,
            document_id: 101,
            page_number: 9,
            chunk_index: 22,
            distance: 0.15,
            snippet: null,
          },
        ]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    );

    expect(
      screen.getByTestId("citation-evidence-location"),
    ).toHaveTextContent(
      "Evidence is available on Page 9",
    );
  });

  it("supports independent navigation for multiple citations", () => {
    const onCitationClick = vi.fn();

    render(
      <CitationSources
        sources={sources}
        onCitationClick={onCitationClick}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /2 sources/i,
      }),
    );

    const openButtons = screen.getAllByRole("button", {
      name: /open in document/i,
    });

    expect(openButtons).toHaveLength(2);

    fireEvent.click(openButtons[0]);
    fireEvent.click(openButtons[1]);

    expect(onCitationClick).toHaveBeenNthCalledWith(1, sources[0]);
    expect(onCitationClick).toHaveBeenNthCalledWith(2, sources[1]);
  });

  it("collapses again when the source button is clicked", () => {
    render(<CitationSources sources={sources} />);

    const toggle = screen.getByRole("button", {
      name: /2 sources/i,
    });

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("exposes technical retrieval details through the optional details section", () => {
    render(<CitationSources sources={sources} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /2 sources/i,
      }),
    );

    expect(screen.getAllByText("Technical details")).toHaveLength(2);

    fireEvent.click(screen.getAllByText("Technical details")[0]);

    expect(screen.getAllByText("Relevance")[0]).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();

    expect(
      screen.getAllByTestId("citation-chunk")[0],
    ).toHaveTextContent("Chunk 12");
  });

  it("renders unavailable page navigation safely", () => {
    render(
      <CitationSources
        sources={[
          {
            id: 105,
            document_id: 101,
            page_number: null,
            chunk_index: null,
            distance: 0.15,
            snippet: null,
          },
        ]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    );

    expect(screen.getByText("Page unavailable")).toBeInTheDocument();

    expect(
      screen.getByText("Document navigation unavailable"),
    ).toBeInTheDocument();
  });

  it("clamps invalid relevance values safely", () => {
    render(
      <CitationSources
        sources={[
          {
            id: 106,
            document_id: 101,
            page_number: 1,
            chunk_index: 1,
            distance: 2,
            snippet: null,
          },
          {
            id: 107,
            document_id: 101,
            page_number: 2,
            chunk_index: 2,
            distance: -1,
            snippet: null,
          },
        ]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /2 sources/i,
      }),
    );

    const detailSummaries =
      screen.getAllByText("Technical details");

    fireEvent.click(detailSummaries[0]);
    expect(screen.getByText("0%")).toBeInTheDocument();

    fireEvent.click(detailSummaries[1]);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });
});
