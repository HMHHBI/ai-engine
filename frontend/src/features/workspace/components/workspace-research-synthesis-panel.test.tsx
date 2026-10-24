import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceResearchSynthesisPanel } from "./workspace-research-synthesis-panel";
import { useWorkspaceStore } from "../store/workspace-store";
import { workspaceActions } from "../actions/workspace-actions";
import { workspaceService } from "../services/workspace-service";

vi.mock("../actions/workspace-actions", () => ({
  workspaceActions: {
    triggerResearchSynthesis: vi.fn(),
    loadResearchRuns: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../services/workspace-service", () => ({
  workspaceService: {
    downloadResearchExport: vi.fn(),
  },
}));

describe("WorkspaceResearchSynthesisPanel", () => {
  const mockDocs = [
    { document_id: 1, filename: "Paper1.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
    { document_id: 2, filename: "Paper2.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
    { document_id: 3, filename: "Paper3.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.getState().reset();
  });

  it("enforces minimum 2 documents before allowing synthesis submission", () => {
    useWorkspaceStore.setState({
      documentsByWorkspace: { 10: mockDocs },
      researchRunsByWorkspace: { 10: [] },
    });

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    const submitBtn = screen.getByRole("button", { name: /Run Synthesis/i });
    expect(submitBtn).toBeDisabled();

    // Select 1 document
    const check1 = screen.getByLabelText(/Paper1.pdf/i);
    fireEvent.click(check1);
    expect(screen.getByText(/Minimum 2 documents required/i)).toBeDefined();
    expect(submitBtn).toBeDisabled();

    // Select 2nd document
    const check2 = screen.getByLabelText(/Paper2.pdf/i);
    fireEvent.click(check2);
    expect(screen.queryByText(/Minimum 2 documents required/i)).toBeNull();

    // Add query
    const textarea = screen.getByPlaceholderText(/Compare the methodologies/i);
    fireEvent.change(textarea, { target: { value: "Synthesize findings" } });

    expect(submitBtn).not.toBeDisabled();
  });

  it("triggers synthesis and displays answer with citations", async () => {
    useWorkspaceStore.setState({
      documentsByWorkspace: { 10: mockDocs },
      researchRunsByWorkspace: { 10: [] },
    });

    vi.mocked(workspaceActions.triggerResearchSynthesis).mockResolvedValueOnce({
      id: 55,
      workspace_id: 10,
      requester_id: 1,
      query: "Compare papers",
      status: "completed",
      answer: "Cross-document synthesis results",
      citations: [
        {
          citation_id: "c-1",
          document_id: 1,
          filename: "Paper1.pdf",
          chunk_id: 12,
          page_number: 4,
          excerpt: "Attention is all you need.",
        },
      ],
      run_metadata: {},
      created_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
    });

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    fireEvent.click(screen.getByLabelText(/Paper1.pdf/i));
    fireEvent.click(screen.getByLabelText(/Paper2.pdf/i));
    fireEvent.change(screen.getByPlaceholderText(/Compare the methodologies/i), {
      target: { value: "Compare papers" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Run Synthesis/i }));

    expect(workspaceActions.triggerResearchSynthesis).toHaveBeenCalledWith(10, {
      query: "Compare papers",
      document_ids: [1, 2],
    });

    expect(await screen.findByText("Cross-document synthesis results")).toBeDefined();
    expect(screen.getByText(/Attention is all you need/i)).toBeDefined();
    expect(screen.getByText(/Page 4/i)).toBeDefined();
  });

  it("renders structured 5 facets when facets object is present", () => {
    useWorkspaceStore.setState({
      documentsByWorkspace: { 10: mockDocs },
      researchRunsByWorkspace: {
        10: [
          {
            id: 99,
            workspace_id: 10,
            requester_id: 1,
            query: "5-facet comparative query",
            status: "completed",
            answer: "Legacy markdown answer",
            facets: {
              methodology: "Attention-based comparative methodology",
              datasets: "GLUE and SQuAD 2.0 evaluation sets",
              metrics: "Accuracy and latency metrics recorded",
              findings: "Transformer models scaled reliably",
              limitations: "Quadratic memory complexity remains",
            },
            citations: [],
            run_metadata: {},
            created_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
          },
        ],
      },
    });

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    expect(screen.getByTestId("structured-facets-container")).toBeDefined();
    expect(screen.getByTestId("facet-card-methodology")).toBeDefined();
    expect(screen.getByText("Attention-based comparative methodology")).toBeDefined();
    expect(screen.getByText("GLUE and SQuAD 2.0 evaluation sets")).toBeDefined();
    expect(screen.getByText("Accuracy and latency metrics recorded")).toBeDefined();
    expect(screen.getByText("Transformer models scaled reliably")).toBeDefined();
    expect(screen.getByText("Quadratic memory complexity remains")).toBeDefined();
  });

  it("handles markdown and json export actions", async () => {
    vi.mocked(workspaceService.downloadResearchExport).mockResolvedValue(undefined);

    useWorkspaceStore.setState({
      documentsByWorkspace: { 10: mockDocs },
      researchRunsByWorkspace: {
        10: [
          {
            id: 88,
            workspace_id: 10,
            requester_id: 1,
            query: "Q",
            status: "completed",
            answer: "Answer text",
            citations: [],
            run_metadata: {},
            created_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
          },
        ],
      },
    });

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    const mdBtn = screen.getByRole("button", { name: /Export Markdown/i });
    fireEvent.click(mdBtn);
    expect(workspaceService.downloadResearchExport).toHaveBeenCalledWith(10, 88, "markdown");

    await vi.waitFor(() => {
      const jsonBtn = screen.getByRole("button", { name: /Export JSON/i });
      expect(jsonBtn).not.toBeDisabled();
      fireEvent.click(jsonBtn);
    });

    expect(workspaceService.downloadResearchExport).toHaveBeenCalledWith(10, 88, "json");
  });

  it("reconciles state and resets selections when switching workspaces without unmounting", () => {
    const ws1Docs = [
      { document_id: 1, filename: "Paper1.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
      { document_id: 2, filename: "Paper2.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
    ];
    const ws2Docs = [
      { document_id: 10, filename: "Paper10.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
      { document_id: 20, filename: "Paper20.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
    ];

    useWorkspaceStore.setState({
      documentsByWorkspace: { 1: ws1Docs, 2: ws2Docs },
      researchRunsByWorkspace: {
        1: [
          {
            id: 101,
            workspace_id: 1,
            requester_id: 1,
            query: "Q1",
            status: "completed",
            answer: "Workspace 1 Answer",
            citations: [],
            run_metadata: {},
            created_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
          },
        ],
        2: [
          {
            id: 202,
            workspace_id: 2,
            requester_id: 1,
            query: "Q2",
            status: "completed",
            answer: "Workspace 2 Answer",
            citations: [],
            run_metadata: {},
            created_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
          },
        ],
      },
    });

    const { rerender } = render(<WorkspaceResearchSynthesisPanel workspaceId={1} />);

    expect(screen.getByText("Workspace 1 Answer")).toBeDefined();
    expect(screen.getByText("Run #101 Output")).toBeDefined();

    fireEvent.click(screen.getByLabelText(/Paper1.pdf/i));

    rerender(<WorkspaceResearchSynthesisPanel workspaceId={2} />);

    expect(screen.queryByText("Workspace 1 Answer")).toBeNull();
    expect(screen.getByText("Workspace 2 Answer")).toBeDefined();
    expect(screen.getByText("Run #202 Output")).toBeDefined();

    const checkWs2 = screen.getByLabelText(/Paper10.pdf/i) as HTMLInputElement;
    expect(checkWs2.checked).toBe(false);
  });

  it("drops detached documents from selection and disables submission if count falls below 2", () => {
    const initialDocs = [
      { document_id: 1, filename: "Paper1.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
      { document_id: 2, filename: "Paper2.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
    ];

    useWorkspaceStore.setState({
      documentsByWorkspace: { 10: initialDocs },
      researchRunsByWorkspace: { 10: [] },
    });

    const { rerender } = render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    fireEvent.click(screen.getByLabelText(/Paper1.pdf/i));
    fireEvent.click(screen.getByLabelText(/Paper2.pdf/i));
    fireEvent.change(screen.getByPlaceholderText(/Compare the methodologies/i), {
      target: { value: "Synthesize" },
    });

    const submitBtn = screen.getByRole("button", { name: /Run Synthesis/i });
    expect(submitBtn).not.toBeDisabled();

    useWorkspaceStore.setState({
      documentsByWorkspace: {
        10: [initialDocs[0]],
      },
    });

    rerender(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    expect(screen.getByText(/1 \/ 1 selected/i)).toBeDefined();
    expect(screen.getByText(/Minimum 2 documents required/i)).toBeDefined();
    expect(submitBtn).toBeDisabled();
  });
});
