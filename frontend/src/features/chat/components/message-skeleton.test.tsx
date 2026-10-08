import "@testing-library/jest-dom";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageSkeleton } from "./message-skeleton";

describe("MessageSkeleton", () => {
  it("renders geometric user and assistant placeholders without interactive controls", () => {
    const { container } = render(<MessageSkeleton />);

    expect(container.querySelectorAll("button")).toHaveLength(0);
    expect(container.querySelectorAll("textarea")).toHaveLength(0);
    expect(container.querySelectorAll("input")).toHaveLength(0);

    expect(container.querySelectorAll('[class*="animate-pulse"]')).not.toHaveLength(0);
  });
});
