export const PDF_MAX_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB
export const PDF_MIME_TYPE = "application/pdf";
export const IMAGE_MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB
export const ALLOWED_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
];

export function validateImage(file: File): string | null {
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
    return "Unsupported image type. Only JPG, PNG, WEBP, and GIF images are supported.";
  }

  if (file.size === 0) {
    return "The image file is empty.";
  }

  if (file.size > IMAGE_MAX_SIZE_BYTES) {
    return "Image is too large. Images must be 10 MB or smaller.";
  }

  return null;
}

export function validatePdf(file: File): string | null {
  if (file.type !== PDF_MIME_TYPE && !file.name.toLowerCase().endsWith(".pdf")) {
    return "Only PDF files are supported.";
  }

  if (file.size === 0) {
    return "The PDF file is empty.";
  }

  if (file.size > PDF_MAX_SIZE_BYTES) {
    return "PDF is too large. PDF files must be 20 MB or smaller.";
  }

  return null;
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => {
      const result = reader.result;

      if (typeof result !== "string") {
        reject(new Error("Failed to read file as data URL."));
        return;
      }

      const commaIndex = result.indexOf(",");

      if (commaIndex === -1) {
        resolve(result);
        return;
      }

      resolve(result.slice(commaIndex + 1));
    };

    reader.onerror = () => {
      reject(reader.error ?? new Error("File read error."));
    };

    reader.readAsDataURL(file);
  });
}