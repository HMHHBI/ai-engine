import { describe, it, expect, vi, beforeEach } from "vitest";
import { documentApi } from "@/lib/api/documents";
import { apiClient } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
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

  it("calls update with correct path and payload", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      id: 42,
      user_id: 10,
      chat_id: 5,
      filename: "new.pdf",
      mime_type: "application/pdf",
      status: "ready",
    });

    const updated = await documentApi.update(42, { filename: "new.pdf" });
    expect(apiClient.patch).toHaveBeenCalledWith("/documents/42", { filename: "new.pdf" });
    expect(updated.filename).toBe("new.pdf");
  });

  it("calls delete with correct path", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);

    await documentApi.delete(42);
    expect(apiClient.delete).toHaveBeenCalledWith("/documents/42");
  });
});