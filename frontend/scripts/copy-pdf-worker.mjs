import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const frontendRoot = path.resolve(__dirname, "..");
const publicDirectory = path.join(frontendRoot, "public");
const destinationWorker = path.join(publicDirectory, "pdf.worker.min.mjs");

try {
  const pdfjsDistDirectory = path.dirname(
    require.resolve("pdfjs-dist/package.json"),
  );

  const sourceWorker = path.join(
    pdfjsDistDirectory,
    "build",
    "pdf.worker.min.mjs",
  );

  if (fs.existsSync(sourceWorker)) {
    fs.mkdirSync(publicDirectory, { recursive: true });
    fs.copyFileSync(sourceWorker, destinationWorker);

    const sourceSize = fs.statSync(sourceWorker).size;
    const destinationSize = fs.statSync(destinationWorker).size;

    if (sourceSize === destinationSize) {
      console.log(
        `PDF.js worker copied successfully: ${path.relative(frontendRoot, destinationWorker)}`,
      );
      process.exit(0);
    }
  }
} catch (error) {
  // If resolution fails but destination already exists (e.g., in pruned production container), use it
  if (fs.existsSync(destinationWorker) && fs.statSync(destinationWorker).size > 0) {
    console.log(
      `PDF.js worker already present in public directory (${path.relative(frontendRoot, destinationWorker)}). Skipping copy.`,
    );
    process.exit(0);
  }

  console.error("Failed to copy PDF.js worker:", error);
  process.exit(1);
}

if (!fs.existsSync(destinationWorker) || fs.statSync(destinationWorker).size === 0) {
  console.error("PDF.js worker is missing in destination.");
  process.exit(1);
}
