import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/errors/api-error";
import { getUserFacingError } from "@/lib/errors/error-message";

describe("getUserFacingError", () => {
  it("maps UNAUTHORIZED correctly", () => {
    const error = new ApiError("Session expired", "UNAUTHORIZED", 401);
    const result = getUserFacingError(error);

    expect(result.title).toBe("Session Expired");
    expect(result.retryable).toBe(false);
    expect(result.actionLabel).toBe("Sign in");
  });

  it("maps RATE_LIMITED correctly", () => {
    const error = new ApiError("Too many requests", "RATE_LIMITED", 429);
    const result = getUserFacingError(error);

    expect(result.title).toBe("Too Many Requests");
    expect(result.retryable).toBe(true);
  });

  it("maps PROVIDER_DOWN correctly", () => {
    const error = new ApiError("Provider down", "PROVIDER_DOWN", 502);
    const result = getUserFacingError(error);

    expect(result.title).toBe("AI Service Unavailable");
    expect(result.retryable).toBe(true);
  });

  it("maps NETWORK_ERROR correctly", () => {
    const error = new ApiError("Failed to fetch", "NETWORK_ERROR");
    const result = getUserFacingError(error);

    expect(result.title).toBe("Connection Problem");
    expect(result.retryable).toBe(true);
  });

  it("maps STREAM_ERROR correctly", () => {
    const error = new ApiError("Stream broken", "STREAM_ERROR");
    const result = getUserFacingError(error);

    expect(result.title).toBe("Response Incomplete");
    expect(result.retryable).toBe(true);
  });

  it("maps STREAM_ABORTED as not retryable and cancelled", () => {
    const error = new ApiError("User cancelled", "STREAM_ABORTED");
    const result = getUserFacingError(error);

    expect(result.title).toBe("Cancelled");
    expect(result.retryable).toBe(false);
  });

  it("handles standard Error instances safely", () => {
    const error = new Error("Custom unexpected failure");
    const result = getUserFacingError(error);

    expect(result.title).toBe("Something Went Wrong");
    expect(result.message).toBe("Custom unexpected failure");
  });
});