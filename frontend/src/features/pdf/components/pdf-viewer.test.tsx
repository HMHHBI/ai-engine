import { describe, expect, it } from "vitest";
import { clampPage } from "@/features/pdf/utils/pdf-viewer-utils";

describe("clampPage", () => {
  it("P6: keeps page 1 at the lower bound", () => {
    expect(clampPage(1, 10)).toBe(1);
  });

  it("P7: advances to a valid next page", () => {
    expect(clampPage(2, 10)).toBe(2);
  });

  it("P8: prevents navigation below page 1", () => {
    expect(clampPage(0, 10)).toBe(1);
    expect(clampPage(-1, 10)).toBe(1);
  });

  it("P9: prevents navigation beyond the last page", () => {
    expect(clampPage(11, 10)).toBe(10);
    expect(clampPage(100, 10)).toBe(10);
  });

  it("P10: keeps the final page within the upper bound", () => {
    expect(clampPage(10, 10)).toBe(10);
  });
});
