import "@testing-library/jest-dom";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { DocumentUpload } from "./components/DocumentUpload";
import { useDocumentStore } from "./document-store";
import * as actions from "./document-actions";

describe("DocumentUpload Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDocumentStore.getState().reset();
  });

  it("renders upload button in idle state", () => {
    render(<DocumentUpload chatId={1} />);
    expect(screen.getByTestId("document-upload-button")).toHaveTextContent(
      "Upload PDF",
    );
  });

  it("rejects non-PDF files client-side", async () => {
    render(<DocumentUpload chatId={1} />);
    const input = screen.getByTestId("document-upload-file-input");

    const textFile = new File(["sample"], "note.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [textFile] } });

    await waitFor(() => {
      expect(screen.getByTestId("document-upload-error")).toHaveTextContent(
        "Only PDF files are supported.",
      );
    });
  });

  it("rejects empty files client-side", async () => {
    render(<DocumentUpload chatId={1} />);
    const input = screen.getByTestId("document-upload-file-input");

    const emptyFile = new File([], "empty.pdf", { type: "application/pdf" });
    fireEvent.change(input, { target: { files: [emptyFile] } });

    await waitFor(() => {
      expect(screen.getByTestId("document-upload-error")).toHaveTextContent(
        "File is empty.",
      );
    });
  });

  it("calls uploadDocument and reflects upload trigger", () => {
    const uploadSpy = vi
      .spyOn(actions, "uploadDocument")
      .mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 50)),
      );

    render(<DocumentUpload chatId={1} />);
    const input = screen.getByTestId("document-upload-file-input");

    const validPdf = new File(["%PDF-1.4 content"], "file.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(input, { target: { files: [validPdf] } });

    expect(uploadSpy).toHaveBeenCalledWith(1, validPdf);
  });
});
