"use client";

import { useEffect, useRef, useState } from "react";
import { documentApi } from "@/lib/api/documents";
import { ApiError } from "@/lib/errors/api-error";
import type {
  PdfDocumentError,
  PdfDocumentState,
} from "@/features/pdf/types/pdf";

function getError(error: unknown): PdfDocumentError {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "NOT_FOUND":
        return {
          code: "NOT_FOUND",
          message: "The requested PDF could not be found.",
          status: error.status,
        };

      case "UNAUTHORIZED":
        return {
          code: "UNAUTHORIZED",
          message: "You are not authorized to access this PDF.",
          status: error.status,
        };

      case "NETWORK_ERROR":
        return {
          code: "NETWORK_ERROR",
          message: "The PDF could not be loaded because of a network error.",
        };

      case "SERVER_ERROR":
        return {
          code: "SERVER_ERROR",
          message: "The server could not provide the PDF.",
          status: error.status,
        };

      default:
        return {
          code: "UNKNOWN",
          message: error.message || "The PDF could not be loaded.",
          status: error.status,
        };
    }
  }

  return {
    code: "UNKNOWN",
    message:
      error instanceof Error && error.message
        ? error.message
        : "The PDF could not be loaded.",
  };
}

function isPdfBlob(blob: Blob): boolean {
  return blob.type === "application/pdf";
}

export interface UsePdfDocumentResult extends PdfDocumentState {
  objectUrl: string | null;
}

export function usePdfDocument(
  documentId: number | null,
): UsePdfDocumentResult {
  const [state, setState] = useState<UsePdfDocumentResult>({
    status: documentId === null ? "idle" : "loading",
    blob: null,
    objectUrl: null,
    error: null,
  });

  const requestIdRef = useRef(0);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    const requestId = ++requestIdRef.current;
    const controller = new AbortController();

    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }

    if (documentId === null) {
      queueMicrotask(() => {
        if (requestId === requestIdRef.current) {
          setState({
            status: "idle",
            blob: null,
            objectUrl: null,
            error: null,
          });
        }
      });

      return () => {
        controller.abort();
      };
    }

    queueMicrotask(() => {
      if (requestId === requestIdRef.current) {
        setState({
          status: "loading",
          blob: null,
          objectUrl: null,
          error: null,
        });
      }
    });

    const loadDocument = async () => {
      try {
        const blob = await documentApi.getFile(documentId, {
          signal: controller.signal,
        });

        if (
          controller.signal.aborted ||
          requestId !== requestIdRef.current
        ) {
          return;
        }

        if (!isPdfBlob(blob)) {
          setState({
            status: "error",
            blob: null,
            objectUrl: null,
            error: {
              code: "INVALID_PDF",
              message: "The server returned an invalid PDF file.",
            },
          });
          return;
        }

        const objectUrl = URL.createObjectURL(blob);

        if (
          controller.signal.aborted ||
          requestId !== requestIdRef.current
        ) {
          URL.revokeObjectURL(objectUrl);
          return;
        }

        objectUrlRef.current = objectUrl;

        setState({
          status: "loaded",
          blob,
          objectUrl,
          error: null,
        });
      } catch (error) {
        if (
          controller.signal.aborted ||
          requestId !== requestIdRef.current
        ) {
          return;
        }

        setState({
          status: "error",
          blob: null,
          objectUrl: null,
          error: getError(error),
        });
      }
    };

    void loadDocument();

    return () => {
      controller.abort();

      if (requestId === requestIdRef.current) {
        requestIdRef.current += 1;
      }

      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [documentId]);

  return state;
}
