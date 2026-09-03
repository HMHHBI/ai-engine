import { describe, expect, it } from "vitest";

import {
  fileToBase64,
  validateImage,
  validatePdf,
} from "./attachment-utils";

describe("attachment-utils", () => {
  it("validates supported image formats", () => {
    const pngFile = new File(["test"], "sample.png", { type: "image/png" });
    const jpegFile = new File(["test"], "sample.jpg", { type: "image/jpeg" });
    const webpFile = new File(["test"], "sample.webp", { type: "image/webp" });

    expect(validateImage(pngFile)).toBeNull();
    expect(validateImage(jpegFile)).toBeNull();
    expect(validateImage(webpFile)).toBeNull();
  });

  it("rejects unsupported image types", () => {
    const svgFile = new File(["test"], "sample.svg", { type: "image/svg+xml" });
    expect(validateImage(svgFile)).toContain("Unsupported image type");
  });

  it("rejects images exceeding size limit", () => {
    const largeFile = new File(["x"], "large.png", { type: "image/png" });
    Object.defineProperty(largeFile, "size", { value: 11 * 1024 * 1024 });

    expect(validateImage(largeFile)).toContain("Image is too large");
  });

  it("validates PDF type and size limit", () => {
    const validPdf = new File(["%PDF-1.4"], "doc.pdf", {
      type: "application/pdf",
    });
    expect(validatePdf(validPdf)).toBeNull();

    const invalidPdf = new File(["text"], "doc.txt", { type: "text/plain" });
    expect(validatePdf(invalidPdf)).toContain("Only PDF files are supported");

    const largePdf = new File(["x"], "large.pdf", { type: "application/pdf" });
    Object.defineProperty(largePdf, "size", { value: 21 * 1024 * 1024 });
    expect(validatePdf(largePdf)).toContain("PDF is too large");
  });

  it("converts a file to base64", async () => {
    const file = new File(["hello world"], "test.txt", { type: "text/plain" });
    const base64 = await fileToBase64(file);
    expect(typeof base64).toBe("string");
    expect(base64.length).toBeGreaterThan(0);
  });
});