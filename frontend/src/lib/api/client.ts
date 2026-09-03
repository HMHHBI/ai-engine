import { ApiError } from "@/lib/errors/api-error";

function getApiUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }
  return url;
}

type RequestOptions = RequestInit & {
  skipAuth?: boolean;
};

function getToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  return localStorage.getItem("token");
}

function buildUrl(path: string): string {
  return `${getApiUrl().replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }

  try {
    return await response.text();
  } catch {
    return null;
  }
}

function getErrorMessage(body: unknown, fallback: string): string {
  if (typeof body === "string" && body.trim()) {
    return body;
  }

  if (typeof body === "object" && body !== null) {
    const data = body as Record<string, unknown>;

    if (typeof data.detail === "string") {
      return data.detail;
    }

    if (typeof data.message === "string") {
      return data.message;
    }

    if (typeof data.error === "string") {
      return data.error;
    }
  }

  return fallback;
}

function mapStatusToCode(status: number): string {
  switch (status) {
    case 401:
      return "UNAUTHORIZED";
    case 413:
      return "FILE_TOO_LARGE";
    case 429:
      return "RATE_LIMITED";
    case 502:
    case 503:
    case 504:
      return "PROVIDER_DOWN";
    default:
      return "UNKNOWN";
  }
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { skipAuth = false, headers, ...fetchOptions } = options;

  const requestHeaders = new Headers(headers);

  if (!requestHeaders.has("Accept")) {
    requestHeaders.set("Accept", "application/json");
  }

  const isFormData = fetchOptions.body instanceof FormData;

  if (fetchOptions.body && !isFormData && !requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }

  if (!skipAuth) {
    const token = getToken();

    if (token) {
      requestHeaders.set("Authorization", `Bearer ${token}`);
    }
  }

  let response: Response;

  try {
    response = await fetch(buildUrl(path), {
      ...fetchOptions,
      headers: requestHeaders,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }

    throw new ApiError(
      "Network request failed.",
      "NETWORK_ERROR",
      undefined,
      error,
    );
  }

  const body = await parseResponseBody(response);

  if (!response.ok) {
    const code = mapStatusToCode(response.status);

    throw new ApiError(
      getErrorMessage(body, `Request failed with status ${response.status}.`),
      code,
      response.status,
      body,
    );
  }

  return body as T;
}

export const apiClient = {
  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, {
      ...options,
      method: "GET",
    });
  },

  post<T>(
    path: string,
    body?: unknown,
    options?: RequestOptions,
  ): Promise<T> {
    return request<T>(path, {
      ...options,
      method: "POST",
      body:
        body instanceof FormData
          ? body
          : body !== undefined
            ? JSON.stringify(body)
            : undefined,
    });
  },

  put<T>(
    path: string,
    body?: unknown,
    options?: RequestOptions,
  ): Promise<T> {
    return request<T>(path, {
      ...options,
      method: "PUT",
      body:
        body instanceof FormData
          ? body
          : body !== undefined
            ? JSON.stringify(body)
            : undefined,
    });
  },

  delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, {
      ...options,
      method: "DELETE",
    });
  },
};