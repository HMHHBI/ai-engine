import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageSkeleton } from "./message-skeleton";

describe("MessageSkeleton", () => {
  it("renders geometric user and assistant placeholders without interactive controls", () => {
    render(<MessageSkeleton />);

    const skeleton = screen.getByTestId("message-skeleton");
    expect(skeleton).toBeInTheDocument();
    expect(skeleton).toHaveAttribute("aria-hidden", "true");

    expect(skeleton.querySelectorAll("button")).toHaveLength(0);
    expect(skeleton.querySelectorAll("textarea")).toHaveLength(0);
    expect(skeleton.querySelectorAll("input")).toHaveLength(0);
    expect(skeleton.querySelectorAll("a")).toHaveLength(0);
  });
});
