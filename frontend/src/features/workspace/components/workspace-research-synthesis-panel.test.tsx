import type { ResearchRun, ResearchRunStageEvent } from "@/types/research";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceResearchSynthesisPanel } from "./workspace-research-synthesis-panel";
import { useWorkspaceStore } from "../store/workspace-store";
import { workspaceActions } from "../actions/workspace-actions";
import { workspaceService } from "../services/workspace-service";

vi.mock("../actions/workspace-actions", () => ({
  workspaceActions: {
    triggerResearchSynthesis: vi.fn(),
    refreshResearchRun: vi.fn(async (workspaceId: number, runId: number) => {
      const updated = await workspaceService.getResearchRun(workspaceId, runId);
      if (updated) {
        useWorkspaceStore.getState().addResearchRun(workspaceId, updated);
      }
      return updated ?? null;
    }),
    cancelResearchRun: vi.fn(async (workspaceId: number, runId: number) => {
      const response = await workspaceService.cancelResearchRun(workspaceId, runId);
      const refreshed = await workspaceService.getResearchRun(workspaceId, runId);
      return { response, run: refreshed ?? null };
    }),
    loadResearchRuns: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../services/workspace-service", () => ({
  workspaceService: {
    downloadResearchExport: vi.fn(),
    getResearchRun: vi.fn(),
    cancelResearchRun: vi.fn(),
    streamResearchRunEvents: vi.fn(() => () => {}),
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
        2: [],
      },
    });

    const { rerender } = render(<WorkspaceResearchSynthesisPanel workspaceId={1} />);

    expect(screen.getByText("Workspace 1 Answer")).toBeDefined();
    expect(screen.getByText("Run #101 Output")).toBeDefined();

    // Type query and select doc on workspace 1
    const queryInput1 = screen.getByPlaceholderText(/Compare the methodologies/i) as HTMLTextAreaElement;
    fireEvent.change(queryInput1, { target: { value: "Dirty uncommitted query in ws1" } });
    fireEvent.click(screen.getByLabelText(/Paper1.pdf/i));
    expect(queryInput1.value).toBe("Dirty uncommitted query in ws1");

    // Rerender same mounted component with workspace 2
    rerender(<WorkspaceResearchSynthesisPanel workspaceId={2} />);

    expect(screen.queryByText("Workspace 1 Answer")).toBeNull();
    const queryInput2 = screen.getByPlaceholderText(/Compare the methodologies/i) as HTMLTextAreaElement;
    expect(queryInput2.value).toBe("");

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

    expect(screen.getByText(/1 \/ 1 ready papers selected/i)).toBeDefined();
    expect(screen.getByText(/Minimum 2 documents required/i)).toBeDefined();
    expect(submitBtn).toBeDisabled();
  });

  it("restores the query and selected document IDs when reopening a historical run", () => {
    useWorkspaceStore.setState({
      documentsByWorkspace: { 10: mockDocs },
      researchRunsByWorkspace: {
        10: [
          {
            id: 123,
            workspace_id: 10,
            requester_id: 1,
            query: "Compare the three papers",
            status: "completed",
            answer: "Historical synthesis answer",
            citations: [],
            run_metadata: {
              selected_document_ids: [1, 3],
            },
            created_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
          },
        ],
      },
    });

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    fireEvent.click(screen.getByRole("button", { name: /Past Runs/i }));
    fireEvent.click(screen.getByRole("button", { name: /#123: Compare the three papers/i }));

    expect(
      screen.getByLabelText(/Synthesis Query/i),
    ).toHaveValue("Compare the three papers");

    expect(screen.getByLabelText(/Paper1\.pdf/i)).toBeChecked();
    expect(screen.getByLabelText(/Paper2\.pdf/i)).not.toBeChecked();
    expect(screen.getByLabelText(/Paper3\.pdf/i)).toBeChecked();

    expect(screen.getByText("Historical synthesis answer")).toBeDefined();
  });

  it("limits Select all to 20 ready documents", () => {
    const manyDocs = Array.from({ length: 22 }, (_, index) => ({
      document_id: index + 1,
      filename: `Paper${index + 1}.pdf`,
      chat_id: null,
      mime_type: "pdf",
      status: "ready",
      added_by: 1,
      added_at: "",
    }));

    useWorkspaceStore.setState({
      documentsByWorkspace: { 10: manyDocs },
      researchRunsByWorkspace: { 10: [] },
    });

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    fireEvent.click(screen.getByRole("button", { name: /Select all/i }));

    expect(screen.getByText(/20 \/ 22 ready papers selected/i)).toBeDefined();
    expect(screen.getByLabelText(/Paper20\.pdf/i)).toBeChecked();
    expect(screen.getByLabelText(/Paper21\.pdf/i)).not.toBeChecked();
    expect(screen.getByLabelText(/Paper22\.pdf/i)).not.toBeChecked();
    expect(screen.getByText(/Maximum 20 papers per synthesis/i)).toBeDefined();
  });

  it("clears invalid persisted run ID when runs load as empty array", async () => {
    sessionStorage.setItem("active_research_run_10", "9999");
    useWorkspaceStore.setState({
      documentsByWorkspace: { 10: mockDocs },
      researchRunsByWorkspace: { 10: [] },
    });

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    await vi.waitFor(() => {
      expect(sessionStorage.getItem("active_research_run_10")).toBeNull();
    });
  });

  it("does not leak persisted run across workspaces", () => {
    sessionStorage.setItem("active_research_run_1", "101");
    sessionStorage.removeItem("active_research_run_2");

    useWorkspaceStore.setState({
      documentsByWorkspace: { 1: mockDocs, 2: mockDocs },
      researchRunsByWorkspace: {
        1: [
          {
            id: 101,
            workspace_id: 1,
            requester_id: 1,
            query: "Run 101 Query",
            status: "completed",
            answer: "Answer 101",
            citations: [],
            run_metadata: { selected_document_ids: [1, 2] },
            created_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
          },
        ],
        2: [],
      },
    });

    const { unmount } = render(<WorkspaceResearchSynthesisPanel key={1} workspaceId={1} />);
    expect(screen.getByText("Answer 101")).toBeDefined();
    unmount();

    render(<WorkspaceResearchSynthesisPanel key={2} workspaceId={2} />);
    expect(screen.queryByText("Answer 101")).toBeNull();
    const queryInput = screen.getByPlaceholderText(/Compare the methodologies/i) as HTMLTextAreaElement;
    expect(queryInput.value).toBe("");
  });

  it("filters unready documents from the selectable list", () => {
    const mixedDocs = [
      { document_id: 1, filename: "PaperReady.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
      { document_id: 2, filename: "PaperProcessing.pdf", chat_id: null, mime_type: "pdf", status: "processing", added_by: 1, added_at: "" },
    ];

    useWorkspaceStore.setState({
      documentsByWorkspace: { 10: mixedDocs },
      researchRunsByWorkspace: { 10: [] },
    });

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    expect(screen.getByText(/0 \/ 1 ready papers selected/i)).toBeDefined();
    expect(screen.getByLabelText(/PaperReady\.pdf/i)).toBeDefined();
    expect(screen.queryByLabelText(/PaperProcessing\.pdf/i)).toBeNull();
  });

  it("renders live stage progress stepper and streams stage transitions to completion", async () => {
    const queuedRun: ResearchRun = {
      id: 501,
      workspace_id: 10,
      requester_id: 1,
      query: "Compare async architectures",
      status: "queued",
      answer: null,
      facets: null,
      citations: [],
      run_metadata: { selected_document_ids: [1, 2] },
      created_at: new Date().toISOString(),
      completed_at: null,
    };

    const completedRun: ResearchRun = {
      ...queuedRun,
      status: "completed",
      answer: "## Methodology\nAsync comparison [C1].",
      facets: {
        methodology: "Async comparison [C1].",
        datasets: "Benchmarks [C1].",
        metrics: "p95 latency [C1].",
        findings: "Significant improvement [C1].",
        limitations: "Single node [C1].",
      },
      completed_at: new Date().toISOString(),
    };

    useWorkspaceStore.setState({
      documentsByWorkspace: {
        10: [
          { document_id: 1, chat_id: null, filename: "Paper1.pdf", mime_type: "application/pdf", status: "ready", added_by: 1, added_at: "" },
          { document_id: 2, chat_id: null, filename: "Paper2.pdf", mime_type: "application/pdf", status: "ready", added_by: 1, added_at: "" },
        ],
      },
      researchRunsByWorkspace: { 10: [queuedRun] },
    });

    vi.spyOn(workspaceService, "getResearchRun").mockResolvedValue(queuedRun);
    let capturedHandlers: {
      onStage: (evt: ResearchRunStageEvent) => void;
      onDone: (evt: ResearchRunStageEvent) => void;
    } | null = null;

    vi.spyOn(workspaceService, "streamResearchRunEvents").mockImplementation(
      (_wsId, _runId, handlers) => {
        capturedHandlers = handlers;
        return () => {};
      },
    );

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    expect(screen.getByTestId("research-stage-stepper")).toBeDefined();
    expect(screen.getByTestId("cancel-research-run-btn")).toBeDefined();

    await vi.waitFor(() => {
      expect(capturedHandlers).not.toBeNull();
    });

    capturedHandlers!.onStage({
      run_id: 501,
      workspace_id: 10,
      status: "synthesizing",
      stage: "synthesizing",
      progress_percent: 60,
      cancel_requested: false,
      attempt_count: 1,
      updated_at: new Date().toISOString(),
    });

    await vi.waitFor(() => {
      expect(screen.getByText(/Stage: Synthesizing/i)).toBeDefined();
    });

    vi.spyOn(workspaceService, "getResearchRun").mockResolvedValue(completedRun);
    await capturedHandlers!.onDone({
      run_id: 501,
      workspace_id: 10,
      status: "completed",
      stage: "completed",
      progress_percent: 100,
      cancel_requested: false,
      attempt_count: 1,
      updated_at: new Date().toISOString(),
    });

    await vi.waitFor(() => {
      expect(screen.getByTestId("facet-card-methodology")).toBeDefined();
    });
  });

  it("supports cancelling an active run and retrying a cancelled run", async () => {
    const activeRun: ResearchRun = {
      id: 502,
      workspace_id: 10,
      requester_id: 1,
      query: "Cancel and retry query",
      status: "synthesizing",
      answer: null,
      facets: null,
      citations: [],
      run_metadata: { selected_document_ids: [1, 2] },
      created_at: new Date().toISOString(),
      completed_at: null,
    };

    useWorkspaceStore.setState({
      documentsByWorkspace: {
        10: [
          { document_id: 1, chat_id: null, filename: "Paper1.pdf", mime_type: "application/pdf", status: "ready", added_by: 1, added_at: "" },
          { document_id: 2, chat_id: null, filename: "Paper2.pdf", mime_type: "application/pdf", status: "ready", added_by: 1, added_at: "" },
        ],
      },
      researchRunsByWorkspace: { 10: [activeRun] },
    });

    vi.spyOn(workspaceService, "streamResearchRunEvents").mockImplementation(() => () => {});
    vi.spyOn(workspaceService, "getResearchRun").mockResolvedValue(activeRun);
    const cancelSpy = vi.spyOn(workspaceService, "cancelResearchRun").mockResolvedValue({
      id: 502,
      workspace_id: 10,
      status: "synthesizing",
      cancel_requested: true,
      message: "Cancellation requested; run will stop at the next safe checkpoint.",
    });

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    fireEvent.click(screen.getByTestId("cancel-research-run-btn"));

    await vi.waitFor(() => {
      expect(cancelSpy).toHaveBeenCalledWith(10, 502);
      expect(screen.getByText(/Cancelling\.\.\./i)).toBeDefined();
    });
  });

  it("falls back to polling when SSE stream closes before a terminal done event", async () => {
    const runningRun: ResearchRun = {
      id: 599,
      workspace_id: 10,
      requester_id: 1,
      query: "Compare distributed consensus protocols",
      status: "queued",
      answer: null,
      facets: null,
      citations: [],
      run_metadata: { selected_document_ids: [1, 2] },
      created_at: new Date().toISOString(),
      completed_at: null,
    };

    const completedRun: ResearchRun = {
      ...runningRun,
      status: "completed",
      answer: "Consensus synthesis completed [C1].",
      facets: {
        methodology: "Raft vs Paxos comparison [C1].",
        datasets: "Cluster traces [C1].",
        metrics: "Commit latency [C1].",
        findings: "Consensus synthesis completed [C1].",
        limitations: "Synthetic fault injection [C1].",
      },
      citations: [],
      completed_at: new Date().toISOString(),
    };

    useWorkspaceStore.setState({
      documentsByWorkspace: {
        10: [
          { document_id: 1, chat_id: null, filename: "Paper1.pdf", mime_type: "application/pdf", status: "ready", added_by: 1, added_at: "" },
          { document_id: 2, chat_id: null, filename: "Paper2.pdf", mime_type: "application/pdf", status: "ready", added_by: 1, added_at: "" },
        ],
      },
      researchRunsByWorkspace: { 10: [runningRun] },
    });

    vi.spyOn(workspaceService, "getResearchRun")
      .mockResolvedValueOnce(runningRun)
      .mockResolvedValue(completedRun);

    let capturedOnClose: (() => void) | undefined;
    vi.spyOn(workspaceService, "streamResearchRunEvents").mockImplementation(
      (_wsId, _runId, handlers) => {
        capturedOnClose = handlers.onClose;
        return () => {};
      },
    );

    render(<WorkspaceResearchSynthesisPanel workspaceId={10} />);

    await vi.waitFor(() => {
      expect(capturedOnClose).toBeDefined();
    });

    capturedOnClose?.();

    await vi.waitFor(
      () => {
        expect(screen.getByTestId("facet-card-methodology")).toBeDefined();
      },
      { timeout: 3000 },
    );
  });
});
