import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname) } },
  test: {
    environment: "jsdom",
    // Axe on the full dashboard can exceed five seconds on shared 2-core CI runners.
    testTimeout: 15000,
    maxWorkers: 2,
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    css: false,
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", "e2e/**", ".next/**", "out/**"],
  },
});
