import { beforeEach, describe, expect, it, vi } from "vitest";
import { documentApi } from "@/lib/api/documents";
import { apiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/errors/api-error";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    getBlob: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("documentApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls listForChat with correct path and returns normalized list", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce([
      {
        id: 1,
        user_id: 10,
        chat_id: 5,
        filename: "test.pdf",
        mime_type: "application/pdf",
        file_size: 1024,
        page_count: 2,
        storage_url: null,
        status: "ready",
        error_message: null,
        created_at: "2026-09-06T00:00:00Z",
        updated_at: "2026-09-06T00:00:00Z",
      },
    ]);

    const result = await documentApi.listForChat(5);

    expect(apiClient.get).toHaveBeenCalledWith("/documents/chat/5");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe(1);
    expect(result[0].status).toBe("ready");
  });

  it("calls get with correct path", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      id: 42,
      user_id: 10,
      chat_id: 5,
      filename: "sample.pdf",
      mime_type: "application/pdf",
      status: "ready",
    });

    const doc = await documentApi.get(42);

    expect(apiClient.get).toHaveBeenCalledWith("/documents/42");
    expect(doc.id).toBe(42);
    expect(doc.filename).toBe("sample.pdf");
  });

  describe("getFile", () => {
    it("returns the PDF Blob for a successful 200 response", async () => {
      const blob = new Blob(["%PDF-1.7"], {
        type: "application/pdf",
      });

      vi.mocked(apiClient.getBlob).mockResolvedValueOnce(blob);

      const result = await documentApi.getFile(42);

      expect(apiClient.getBlob).toHaveBeenCalledWith(
        "/documents/42/file",
      );
      expect(result).toBe(blob);
      expect(result.type).toBe("application/pdf");
    });

    it("propagates a 404 Not Found error", async () => {
      const error = new ApiError(
        "Document not found.",
        "NOT_FOUND",
        404,
      );

      vi.mocked(apiClient.getBlob).mockRejectedValueOnce(error);

      await expect(documentApi.getFile(42)).rejects.toMatchObject({
        name: "ApiError",
        code: "NOT_FOUND",
        status: 404,
      });

      expect(apiClient.getBlob).toHaveBeenCalledWith(
        "/documents/42/file",
      );
    });

    it("propagates 401 Unauthorized errors", async () => {
      const error = new ApiError(
        "Authentication required.",
        "UNAUTHORIZED",
        401,
      );

      vi.mocked(apiClient.getBlob).mockRejectedValueOnce(error);

      await expect(documentApi.getFile(42)).rejects.toMatchObject({
        name: "ApiError",
        code: "UNAUTHORIZED",
        status: 401,
      });
    });

    it("propagates 403 Forbidden errors as Unauthorized", async () => {
      const error = new ApiError(
        "Access denied.",
        "UNAUTHORIZED",
        403,
      );

      vi.mocked(apiClient.getBlob).mockRejectedValueOnce(error);

      await expect(documentApi.getFile(42)).rejects.toMatchObject({
        name: "ApiError",
        code: "UNAUTHORIZED",
        status: 403,
      });
    });

    it("propagates 500 Server errors", async () => {
      const error = new ApiError(
        "Server error.",
        "SERVER_ERROR",
        500,
      );

      vi.mocked(apiClient.getBlob).mockRejectedValueOnce(error);

      await expect(documentApi.getFile(42)).rejects.toMatchObject({
        name: "ApiError",
        code: "SERVER_ERROR",
        status: 500,
      });
    });

    it("propagates network failures", async () => {
      const error = new ApiError(
        "Network request failed.",
        "NETWORK_ERROR",
      );

      vi.mocked(apiClient.getBlob).mockRejectedValueOnce(error);

      await expect(documentApi.getFile(42)).rejects.toMatchObject({
        name: "ApiError",
        code: "NETWORK_ERROR",
      });
    });
  });

  it("calls update with correct path and payload", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      id: 42,
      user_id: 10,
      chat_id: 5,
      filename: "new.pdf",
      mime_type: "application/pdf",
      status: "ready",
    });

    const updated = await documentApi.update(42, {
      filename: "new.pdf",
    });

    expect(apiClient.patch).toHaveBeenCalledWith(
      "/documents/42",
      { filename: "new.pdf" },
    );
    expect(updated.filename).toBe("new.pdf");
  });

  it("calls delete with correct path", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);

    await documentApi.delete(42);

    expect(apiClient.delete).toHaveBeenCalledWith(
      "/documents/42",
    );
  });
});
