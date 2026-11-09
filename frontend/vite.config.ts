/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  // Read the root .env (only VITE_* variables reach the browser).
  envDir: "..",
  server: {
    port: 5173,
    proxy: { "/api": backend, "/media": backend },
  },
  test: {
    environment: "jsdom",
  },
});
