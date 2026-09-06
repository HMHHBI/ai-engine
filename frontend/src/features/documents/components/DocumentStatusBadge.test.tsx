import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import React from "react";
import { DocumentStatusBadge } from "./DocumentStatusBadge";

describe("DocumentStatusBadge", () => {
  it("renders ready badge", () => {
    render(<DocumentStatusBadge status="ready" />);
    expect(screen.getByTestId("status-badge-ready")).toHaveTextContent("Ready");
  });

  it("renders processing badge", () => {
    render(<DocumentStatusBadge status="processing" />);
    expect(screen.getByTestId("status-badge-processing")).toHaveTextContent(
      "Processing",
    );
  });

  it("renders failed badge", () => {
    render(<DocumentStatusBadge status="failed" />);
    expect(screen.getByTestId("status-badge-failed")).toHaveTextContent(
      "Failed",
    );
  });
});
