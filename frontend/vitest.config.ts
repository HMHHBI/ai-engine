import { defineConfig, defaultExclude } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    clearMocks: true,
    restoreMocks: true,
    exclude: [...defaultExclude, "e2e/**"],
    server: {
      deps: {
        inline: ["@testing-library/react"],
      },
    },
    env: {
      NEXT_PUBLIC_API_URL: "https://ai-engine-d9lm.onrender.com",
    },
  },

  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "react-dom/test-utils": path.resolve(__dirname, "./src/test/react-dom-test-utils-shim.ts"),
    },
  },
});
