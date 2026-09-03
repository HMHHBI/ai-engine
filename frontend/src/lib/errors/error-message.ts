import { ApiError } from "@/lib/errors/api-error";

export interface UserFacingError {
  title: string;
  message: string;
  retryable: boolean;
  actionLabel?: string;
}

export function getUserFacingError(error: unknown): UserFacingError {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "UNAUTHORIZED":
        return {
          title: "Session Expired",
          message: "Your session has expired. Please sign in again.",
          retryable: false,
          actionLabel: "Sign in",
        };

      case "RATE_LIMITED":
        return {
          title: "Too Many Requests",
          message: "You're sending requests too quickly. Please wait a moment before trying again.",
          retryable: true,
          actionLabel: "Try again",
        };

      case "PROVIDER_DOWN":
        return {
          title: "AI Service Unavailable",
          message: "The AI service is temporarily unavailable. Please try again shortly.",
          retryable: true,
          actionLabel: "Try again",
        };

      case "SERVER_ERROR":
        return {
          title: "Server Error",
          message: "Something went wrong on the server. Please try again.",
          retryable: true,
          actionLabel: "Try again",
        };

      case "NETWORK_ERROR":
        return {
          title: "Connection Problem",
          message: "Unable to connect to the server. Please check your internet connection.",
          retryable: true,
          actionLabel: "Try again",
        };

      case "STREAM_ERROR":
        return {
          title: "Response Incomplete",
          message: "The response was interrupted and could not be completed.",
          retryable: true,
          actionLabel: "Try again",
        };

      case "STREAM_ABORTED":
        return {
          title: "Cancelled",
          message: "The request was cancelled.",
          retryable: false,
        };

      case "FILE_TOO_LARGE":
        return {
          title: "File Too Large",
          message: error.message || "The attached file exceeds the maximum allowed size.",
          retryable: false,
        };

      case "VALIDATION_ERROR":
        return {
          title: "Invalid Input",
          message: error.message || "Please check your inputs and try again.",
          retryable: false,
        };

      default:
        return {
          title: "Something Went Wrong",
          message: error.message || "An unexpected error occurred.",
          retryable: error.retryable ?? true,
          actionLabel: "Try again",
        };
    }
  }

  if (error instanceof Error) {
    return {
      title: "Something Went Wrong",
      message: error.message,
      retryable: true,
      actionLabel: "Try again",
    };
  }

  return {
    title: "Unknown Error",
    message: "An unexpected error occurred. Please try again.",
    retryable: true,
    actionLabel: "Try again",
  };
}