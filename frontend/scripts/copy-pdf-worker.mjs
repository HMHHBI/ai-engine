import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const frontendRoot = path.resolve(__dirname, "..");
const publicDirectory = path.join(frontendRoot, "public");

const pdfjsDistDirectory = path.dirname(
  require.resolve("pdfjs-dist/package.json"),
);

const sourceWorker = path.join(
  pdfjsDistDirectory,
  "build",
  "pdf.worker.min.mjs",
);

const destinationWorker = path.join(
  publicDirectory,
  "pdf.worker.min.mjs",
);

if (!fs.existsSync(sourceWorker)) {
  throw new Error(
    `PDF.js worker not found at expected path: ${sourceWorker}`,
  );
}

fs.mkdirSync(publicDirectory, { recursive: true });

fs.copyFileSync(sourceWorker, destinationWorker);

const sourceSize = fs.statSync(sourceWorker).size;
const destinationSize = fs.statSync(destinationWorker).size;

if (sourceSize !== destinationSize) {
  throw new Error(
    `PDF.js worker copy verification failed. ` +
      `Expected ${sourceSize} bytes, got ${destinationSize} bytes.`,
  );
}

console.log(
  `PDF.js worker copied successfully: ${path.relative(frontendRoot, destinationWorker)}`,
);
