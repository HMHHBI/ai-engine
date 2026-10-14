import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceSwitcher } from "./workspace-switcher";
import { useWorkspaceStore } from "../store/workspace-store";
import { workspaceActions } from "../actions/workspace-actions";

vi.mock("../actions/workspace-actions", () => ({
  workspaceActions: {
    loadWorkspaces: vi.fn(),
    selectWorkspace: vi.fn(),
    createWorkspace: vi.fn(),
  },
}));

describe("WorkspaceSwitcher", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.getState().reset();
  });

  it("renders active workspace name and triggers load on mount", () => {
    useWorkspaceStore.setState({
      workspaces: [{ id: 1, name: "Neural Research", created_by: 1, created_at: "", updated_at: "" }],
      activeWorkspaceId: 1,
    });

    render(<WorkspaceSwitcher />);
    expect(workspaceActions.loadWorkspaces).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Neural Research")).toBeDefined();
  });

  it("opens dropdown and allows selecting another workspace", () => {
    useWorkspaceStore.setState({
      workspaces: [
        { id: 1, name: "Workspace 1", created_by: 1, created_at: "", updated_at: "" },
        { id: 2, name: "Workspace 2", created_by: 1, created_at: "", updated_at: "" },
      ],
      activeWorkspaceId: 1,
    });

    render(<WorkspaceSwitcher />);
    const trigger = screen.getByRole("button", { name: /Workspace: Workspace 1/i });
    fireEvent.click(trigger);

    const option2 = screen.getByRole("button", { name: /Workspace 2/i });
    fireEvent.click(option2);

    expect(workspaceActions.selectWorkspace).toHaveBeenCalledWith(2);
  });

  it("opens dropdown and selects a workspace when rendered in collapsed mode", () => {
    useWorkspaceStore.setState({
      workspaces: [
        { id: 1, name: "Workspace 1", created_by: 1, created_at: "", updated_at: "" },
        { id: 2, name: "Workspace 2", created_by: 1, created_at: "", updated_at: "" },
      ],
      activeWorkspaceId: 1,
    });

    render(<WorkspaceSwitcher collapsed />);
    const trigger = screen.getByRole("button", { name: /Workspace: Workspace 1/i });
    fireEvent.click(trigger);

    // Dialog should open even in collapsed mode
    expect(screen.getByRole("dialog", { name: /Workspaces/i })).toBeDefined();

    const option2 = screen.getByRole("button", { name: /Workspace 2/i });
    fireEvent.click(option2);
    expect(workspaceActions.selectWorkspace).toHaveBeenCalledWith(2);
  });

  it("closes dropdown on Escape key", () => {
    useWorkspaceStore.setState({
      workspaces: [{ id: 1, name: "Workspace 1", created_by: 1, created_at: "", updated_at: "" }],
      activeWorkspaceId: 1,
    });

    render(<WorkspaceSwitcher />);
    const trigger = screen.getByRole("button", { name: /Workspace: Workspace 1/i });
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeDefined();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
