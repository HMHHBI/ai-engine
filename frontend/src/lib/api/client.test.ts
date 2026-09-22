import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api/client";

describe("apiClient.getBlob", () => {
  beforeEach(() => {
    vi.restoreAllMocks();

    vi.stubEnv(
      "NEXT_PUBLIC_API_URL",
      "http://localhost:8000/api",
    );

    localStorage.clear();
  });

  it("returns a Blob for a successful PDF response", async () => {
    const blob = new Blob(["%PDF-1.7"], {
      type: "application/pdf",
    });

    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/pdf" }),
      blob: async () => blob,
    } as unknown as Response);

    const result = await apiClient.getBlob("/documents/42/file");

    expect(result).toBeInstanceOf(Blob);
    expect(result.type).toBe("application/pdf");

    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/documents/42/file",
      expect.objectContaining({
        method: "GET",
        headers: expect.any(Headers),
      }),
    );
  });

  it("maps 404 to NOT_FOUND", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: "Document not found." }),
        {
          status: 404,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    await expect(
      apiClient.getBlob("/documents/42/file"),
    ).rejects.toMatchObject({
      name: "ApiError",
      code: "NOT_FOUND",
      status: 404,
    });
  });

  it("maps 401 to UNAUTHORIZED", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: "Authentication required." }),
        {
          status: 401,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    await expect(
      apiClient.getBlob("/documents/42/file"),
    ).rejects.toMatchObject({
      name: "ApiError",
      code: "UNAUTHORIZED",
      status: 401,
    });
  });

  it("maps 403 to UNAUTHORIZED", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: "Access denied." }),
        {
          status: 403,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    await expect(
      apiClient.getBlob("/documents/42/file"),
    ).rejects.toMatchObject({
      name: "ApiError",
      code: "UNAUTHORIZED",
      status: 403,
    });
  });

  it("maps 500 to SERVER_ERROR", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: "Internal server error." }),
        {
          status: 500,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    await expect(
      apiClient.getBlob("/documents/42/file"),
    ).rejects.toMatchObject({
      name: "ApiError",
      code: "SERVER_ERROR",
      status: 500,
    });
  });

  it("maps network failures to NETWORK_ERROR", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(
      new TypeError("Failed to fetch"),
    );

    await expect(
      apiClient.getBlob("/documents/42/file"),
    ).rejects.toMatchObject({
      name: "ApiError",
      code: "NETWORK_ERROR",
    });
  });
});
