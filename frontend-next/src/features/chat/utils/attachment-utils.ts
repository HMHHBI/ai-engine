const MAX_IMAGE_SIZE = 10 * 1024 * 1024;
const MAX_PDF_SIZE = 20 * 1024 * 1024;

const SUPPORTED_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
] as const;

export function validateImage(file: File): string | null {
  if (
    !SUPPORTED_IMAGE_TYPES.includes(
      file.type as (typeof SUPPORTED_IMAGE_TYPES)[number],
    )
  ) {
    return "Unsupported image type. Use JPG, PNG, WebP, or GIF.";
  }

  if (file.size > MAX_IMAGE_SIZE) {
    return "Image is too large. Maximum size is 10 MB.";
  }

  return null;
}

export function validatePdf(file: File): string | null {
  if (file.type !== "application/pdf") {
    return "Only PDF files are supported.";
  }

  if (file.size > MAX_PDF_SIZE) {
    return "PDF is too large. Maximum size is 20 MB.";
  }

  return null;
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => {
      if (typeof reader.result !== "string") {
        reject(new Error("Unable to read image."));
        return;
      }

      const commaIndex = reader.result.indexOf(",");

      if (commaIndex === -1) {
        reject(new Error("Invalid image data."));
        return;
      }

      resolve(reader.result.slice(commaIndex + 1));
    };

    reader.onerror = () => {
      reject(reader.error ?? new Error("Unable to read image."));
    };

    reader.readAsDataURL(file);
  });
}