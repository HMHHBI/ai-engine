import "@testing-library/jest-dom";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocumentStatusBadge } from "./DocumentStatusBadge";

describe("DocumentStatusBadge", () => {
  it("renders uploading state", () => {
    render(<DocumentStatusBadge status="uploading" />);

    expect(
      screen.getByTestId("status-badge-uploading"),
    ).toHaveTextContent("Uploading");
  });

  it("renders extracting state", () => {
    render(<DocumentStatusBadge status="extracting" />);

    expect(
      screen.getByTestId("status-badge-extracting"),
    ).toHaveTextContent("Extracting Text");
  });

  it("renders indexing state", () => {
    render(<DocumentStatusBadge status="indexing" />);

    expect(
      screen.getByTestId("status-badge-indexing"),
    ).toHaveTextContent("Indexing Evidence");
  });

  it("maps the existing backend processing state to indexing evidence", () => {
    render(<DocumentStatusBadge status="processing" />);

    expect(
      screen.getByTestId("status-badge-indexing"),
    ).toHaveTextContent("Indexing Evidence");
  });

  it("renders ready state", () => {
    render(<DocumentStatusBadge status="ready" />);

    expect(
      screen.getByTestId("status-badge-ready"),
    ).toHaveTextContent("Ready");
  });

  it("renders failed state", () => {
    render(<DocumentStatusBadge status="failed" />);

    expect(
      screen.getByTestId("status-badge-failed"),
    ).toHaveTextContent("Failed");
  });

  it("renders an actionable retry control when provided", () => {
    const onRetry = vi.fn();

    render(
      <DocumentStatusBadge
        status="failed"
        onRetry={onRetry}
      />,
    );

    const retry = screen.getByRole("button", {
      name: /retry document preparation/i,
    });

    expect(retry).toBeInTheDocument();

    retry.click();

    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
