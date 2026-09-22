import { describe, it, expect } from "vitest";
import { parseCandidateDocId } from "./workspace-url";

describe("parseCandidateDocId (M4.2)", () => {
  it("returns null when searchParams is null or undefined", () => {
    expect(parseCandidateDocId(null)).toBeNull();
    expect(parseCandidateDocId(undefined)).toBeNull();
  });

  it("returns null when docId is omitted or empty", () => {
    const params = new URLSearchParams("");
    expect(parseCandidateDocId(params)).toBeNull();

    const emptyParam = new URLSearchParams("docId=");
    expect(parseCandidateDocId(emptyParam)).toBeNull();
  });

  it("returns null for non-numeric or malformed docId", () => {
    expect(parseCandidateDocId(new URLSearchParams("docId=abc"))).toBeNull();
    expect(parseCandidateDocId(new URLSearchParams("docId=12abc"))).toBeNull();
    expect(parseCandidateDocId(new URLSearchParams("docId=12.34"))).toBeNull();
    expect(parseCandidateDocId(new URLSearchParams("docId=true"))).toBeNull();
    expect(parseCandidateDocId(new URLSearchParams("docId=undefined"))).toBeNull();
  });

  it("returns null for zero or negative integers", () => {
    expect(parseCandidateDocId(new URLSearchParams("docId=0"))).toBeNull();
    expect(parseCandidateDocId(new URLSearchParams("docId=-1"))).toBeNull();
    expect(parseCandidateDocId(new URLSearchParams("docId=-999"))).toBeNull();
  });

  it("parses valid positive integer correctly", () => {
    expect(parseCandidateDocId(new URLSearchParams("docId=1"))).toBe(1);
    expect(parseCandidateDocId(new URLSearchParams("docId=123"))).toBe(123);
    expect(parseCandidateDocId(new URLSearchParams("docId=987654"))).toBe(987654);
    expect(parseCandidateDocId(new URLSearchParams("docId= 42 "))).toBe(42);
  });
});
