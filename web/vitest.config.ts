/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

/**
 * Frontend tests. They exist for CareBridge: the language layer decides what a patient
 * reads about their own eyes, and "it looked right when I clicked it" is not a standard
 * this project applies to anything else.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: ["./tests/setup.tsx"],
    // No provider credentials of any kind. Login talks to this project's own API and
    // nothing else, `fetch` is stubbed in every test that exercises it, and there is no
    // SMS gateway the suite could reach even by accident.
    env: {
      NEXT_PUBLIC_API_BASE: "http://api.test",
    },
  },
});
