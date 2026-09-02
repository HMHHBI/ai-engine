export type ErrorCode =
  | "UNAUTHORIZED"
  | "VALIDATION_ERROR"
  | "FILE_TOO_LARGE"
  | "RATE_LIMITED"
  | "PROVIDER_DOWN"
  | "SERVER_ERROR"
  | "NETWORK_ERROR"
  | "STREAM_ERROR"
  | "STREAM_ABORTED"
  | "UNKNOWN";

export class ApiError extends Error {
  public code: ErrorCode | string;
  public status?: number;
  public details?: unknown;
  public retryable: boolean;

  constructor(
    message: string,
    code: ErrorCode | string = "UNKNOWN",
    status?: number,
    details?: unknown,
    retryable = false
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.retryable = retryable || (status ? status === 429 || status >= 500 : false);
  }
}

// Backward compatibility agar APIError ke naam se import ho
export { ApiError as APIError };