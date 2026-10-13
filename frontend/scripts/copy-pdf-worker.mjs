import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const reactPdfWorker = path.join(
  root,
  "node_modules",
  "react-pdf",
  "node_modules",
  "pdfjs-dist",
  "build",
  "pdf.worker.min.mjs"
);
const fallbackWorker = path.join(
  root,
  "node_modules",
  "pdfjs-dist",
  "build",
  "pdf.worker.min.mjs"
);

const src = fs.existsSync(reactPdfWorker) ? reactPdfWorker : fallbackWorker;
const dest = path.join(root, "public", "pdf.worker.min.mjs");

fs.copyFileSync(src, dest);
console.log(`PDF.js worker synchronized from ${src} to ${dest}`);
