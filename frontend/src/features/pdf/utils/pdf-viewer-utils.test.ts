import { describe, expect, it } from "vitest";

import {
  MAX_SCALE,
  MIN_SCALE,
  calculateFitHeightScale,
  calculateFitWidthScale,
  resetZoom,
  zoomIn,
  zoomOut,
} from "@/features/pdf/utils/pdf-viewer-utils";

describe("PDF zoom utilities", () => {
  it("P11: zooms in by the configured step", () => {
    expect(zoomIn(1)).toBe(1.25);
    expect(zoomIn(1.25)).toBe(1.5);
  });

  it("P12: zooms out by the configured step", () => {
    expect(zoomOut(1)).toBe(0.75);
    expect(zoomOut(0.75)).toBe(0.5);
  });

  it("P13: never zooms below the minimum scale", () => {
    expect(zoomOut(MIN_SCALE)).toBe(MIN_SCALE);
    expect(zoomOut(0.25)).toBe(MIN_SCALE);
  });

  it("P14: never zooms above the maximum scale", () => {
    expect(zoomIn(MAX_SCALE)).toBe(MAX_SCALE);
    expect(zoomIn(3.25)).toBe(MAX_SCALE);
  });

  it("resets zoom to 100 percent", () => {
    expect(resetZoom()).toBe(1);
  });
});

describe("PDF fit utilities", () => {
  it("calculates fit-width scale", () => {
    expect(calculateFitWidthScale(600, 1200)).toBe(2);
  });

  it("calculates fit-height scale", () => {
    expect(calculateFitHeightScale(1000, 500)).toBe(0.5);
  });

  it("clamps fit-width scale to the supported range", () => {
    expect(calculateFitWidthScale(100, 1000)).toBe(3);
    expect(calculateFitWidthScale(2000, 100)).toBe(0.5);
  });

  it("falls back safely for invalid dimensions", () => {
    expect(calculateFitWidthScale(0, 1000)).toBe(1);
    expect(calculateFitHeightScale(1000, 0)).toBe(1);
  });
});
