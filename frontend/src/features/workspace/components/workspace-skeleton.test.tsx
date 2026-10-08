import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkspaceSkeleton } from "./workspace-skeleton";

describe("WorkspaceSkeleton", () => {
  it("renders the workspace loading shell", () => {
    render(<WorkspaceSkeleton />);

    expect(screen.getByTestId("workspace-skeleton")).toBeInTheDocument();
  });

  it("contains no interactive controls while the workspace is loading", () => {
    render(<WorkspaceSkeleton />);

    const skeleton = screen.getByTestId("workspace-skeleton");

    expect(skeleton.querySelectorAll("button")).toHaveLength(0);
    expect(skeleton.querySelectorAll("input")).toHaveLength(0);
    expect(skeleton.querySelectorAll("textarea")).toHaveLength(0);
    expect(skeleton.querySelectorAll("select")).toHaveLength(0);
    expect(skeleton.querySelectorAll("a")).toHaveLength(0);
  });

  it("is hidden from assistive technology", () => {
    render(<WorkspaceSkeleton />);

    expect(screen.getByTestId("workspace-skeleton")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });
});
