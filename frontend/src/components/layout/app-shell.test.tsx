import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "./app-shell";

// Mock child components to keep the unit test lightweight and isolated
vi.mock("@/components/layout/app-sidebar", () => ({
  AppSidebar: ({ collapsed }: { collapsed?: boolean }) => (
    <aside data-testid="sidebar" data-collapsed={collapsed ? "true" : "false"}>
      Sidebar
    </aside>
  ),
}));

vi.mock("@/components/layout/app-header", () => ({
  AppHeader: () => <header data-testid="header">Header</header>,
}));

vi.mock("@/features/workspace/components/workspace-controller", () => ({
  WorkspaceController: () => (
    <div>
      <textarea data-chat-composer="true" data-testid="composer" />
    </div>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ chatId: "1" }),
}));

describe("AppShell Global Keyboard Shortcuts", () => {
  it("toggles sidebar on Ctrl+B / Cmd+B", () => {
    render(<AppShell />);

    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.getAttribute("data-collapsed")).toBe("false");

    // Fire Cmd+B
    fireEvent.keyDown(window, { key: "b", metaKey: true });
    expect(sidebar.getAttribute("data-collapsed")).toBe("true");

    // Fire Ctrl+B
    fireEvent.keyDown(window, { key: "b", ctrlKey: true });
    expect(sidebar.getAttribute("data-collapsed")).toBe("false");
  });

  it("does not trigger shortcut when Alt key is also pressed", () => {
    render(<AppShell />);

    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.getAttribute("data-collapsed")).toBe("false");

    fireEvent.keyDown(window, { key: "b", metaKey: true, altKey: true });
    expect(sidebar.getAttribute("data-collapsed")).toBe("false");
  });

  it("focuses composer element on Cmd+K / Ctrl+K", () => {
    render(<AppShell />);

    const composer = screen.getByTestId("composer");
    const focusSpy = vi.spyOn(composer, "focus");

    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(focusSpy).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(composer);

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(focusSpy).toHaveBeenCalledTimes(2);
    expect(document.activeElement).toBe(composer);
  });
  it("renders the workspace controller inside the application shell", () => {
    render(<AppShell />);

    expect(screen.getByTestId("composer")).toBeInTheDocument();
  });
});