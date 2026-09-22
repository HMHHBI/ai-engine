import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { documentApi } from "@/lib/api/documents";
import { ApiError } from "@/lib/errors/api-error";
import { usePdfDocument } from "@/features/pdf/hooks/use-pdf-document";

vi.mock("@/lib/api/documents", () => ({
  documentApi: {
    getFile: vi.fn(),
  },
}));

describe("usePdfDocument", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.spyOn(URL, "createObjectURL").mockReturnValue(
      "blob:http://localhost/pdf-1",
    );

    vi.spyOn(URL, "revokeObjectURL").mockImplementation(
      () => undefined,
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("P1: loads a valid PDF", async () => {
    const blob = new Blob(["%PDF-1.7"], {
      type: "application/pdf",
    });

    vi.mocked(documentApi.getFile).mockResolvedValueOnce(blob);

    const { result } = renderHook(() =>
      usePdfDocument(42),
    );

    expect(result.current.status).toBe("loading");

    await waitFor(() => {
      expect(result.current.status).toBe("loaded");
    });

    expect(result.current.blob).toBe(blob);
    expect(result.current.objectUrl).toBe(
      "blob:http://localhost/pdf-1",
    );
    expect(result.current.error).toBeNull();

    expect(documentApi.getFile).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        signal: expect.any(AbortSignal),
      }),
    );

    expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
  });

  it("P2: exposes NOT_FOUND for a 404 response", async () => {
    vi.mocked(documentApi.getFile).mockRejectedValueOnce(
      new ApiError(
        "Document not found.",
        "NOT_FOUND",
        404,
      ),
    );

    const { result } = renderHook(() =>
      usePdfDocument(42),
    );

    await waitFor(() => {
      expect(result.current.status).toBe("error");
    });

    expect(result.current.error).toEqual({
      code: "NOT_FOUND",
      message: "The requested PDF could not be found.",
      status: 404,
    });
  });

  it("P3: exposes UNAUTHORIZED for an unauthorized response", async () => {
    vi.mocked(documentApi.getFile).mockRejectedValueOnce(
      new ApiError(
        "Authentication required.",
        "UNAUTHORIZED",
        401,
      ),
    );

    const { result } = renderHook(() =>
      usePdfDocument(42),
    );

    await waitFor(() => {
      expect(result.current.status).toBe("error");
    });

    expect(result.current.error).toEqual({
      code: "UNAUTHORIZED",
      message:
        "You are not authorized to access this PDF.",
      status: 401,
    });
  });

  it("P4: rejects a non-PDF Blob as INVALID_PDF", async () => {
    const blob = new Blob(["not a pdf"], {
      type: "text/plain",
    });

    vi.mocked(documentApi.getFile).mockResolvedValueOnce(blob);

    const { result } = renderHook(() =>
      usePdfDocument(42),
    );

    await waitFor(() => {
      expect(result.current.status).toBe("error");
    });

    expect(result.current.error).toEqual({
      code: "INVALID_PDF",
      message: "The server returned an invalid PDF file.",
    });

    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("P5: exposes NETWORK_ERROR for a network failure", async () => {
    vi.mocked(documentApi.getFile).mockRejectedValueOnce(
      new ApiError(
        "Network request failed.",
        "NETWORK_ERROR",
      ),
    );

    const { result } = renderHook(() =>
      usePdfDocument(42),
    );

    await waitFor(() => {
      expect(result.current.status).toBe("error");
    });

    expect(result.current.error).toEqual({
      code: "NETWORK_ERROR",
      message:
        "The PDF could not be loaded because of a network error.",
    });
  });

  it("revokes the object URL when the document changes", async () => {
    const firstBlob = new Blob(["%PDF-1.7"], {
      type: "application/pdf",
    });

    const secondBlob = new Blob(["%PDF-1.7"], {
      type: "application/pdf",
    });

    vi.mocked(URL.createObjectURL)
      .mockReturnValueOnce("blob:first")
      .mockReturnValueOnce("blob:second");

    vi.mocked(documentApi.getFile)
      .mockResolvedValueOnce(firstBlob)
      .mockResolvedValueOnce(secondBlob);

    const { result, rerender } = renderHook(
      ({ documentId }) =>
        usePdfDocument(documentId),
      {
        initialProps: {
          documentId: 1,
        },
      },
    );

    await waitFor(() => {
      expect(result.current.status).toBe("loaded");
    });

    expect(result.current.objectUrl).toBe("blob:first");

    rerender({ documentId: 2 });

    await waitFor(() => {
      expect(result.current.objectUrl).toBe(
        "blob:second",
      );
    });

    expect(URL.revokeObjectURL).toHaveBeenCalledWith(
      "blob:first",
    );
  });

  it("ignores a stale request after document switch", async () => {
    let resolveFirst:
      | ((blob: Blob) => void)
      | undefined;

    const firstPromise = new Promise<Blob>((resolve) => {
      resolveFirst = resolve;
    });

    const secondBlob = new Blob(["%PDF-1.7"], {
      type: "application/pdf",
    });

    vi.mocked(documentApi.getFile)
      .mockReturnValueOnce(firstPromise)
      .mockResolvedValueOnce(secondBlob);

    const { result, rerender } = renderHook(
      ({ documentId }) =>
        usePdfDocument(documentId),
      {
        initialProps: {
          documentId: 1,
        },
      },
    );

    rerender({ documentId: 2 });

    await waitFor(() => {
      expect(result.current.status).toBe("loaded");
    });

    expect(result.current.blob).toBe(secondBlob);

    await act(async () => {
      resolveFirst?.(
        new Blob(["%PDF-OLD"], {
          type: "application/pdf",
        }),
      );
    });

    expect(result.current.blob).toBe(secondBlob);
  });

  it("aborts the request when unmounted", async () => {
    let receivedSignal: AbortSignal | null | undefined;

    vi.mocked(documentApi.getFile).mockImplementation(
      async (_documentId, options) => {
        receivedSignal = options?.signal;

        return new Promise<Blob>(() => undefined);
      },
    );

    const { unmount } = renderHook(() =>
      usePdfDocument(42),
    );

    expect(receivedSignal).toBeDefined();
    expect(receivedSignal?.aborted).toBe(false);

    unmount();

    expect(receivedSignal?.aborted).toBe(true);
  });
});
