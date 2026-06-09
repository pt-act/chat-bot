import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev server proxies API calls to the FastAPI backend so the SPA can run on a
// separate port without CORS friction.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
