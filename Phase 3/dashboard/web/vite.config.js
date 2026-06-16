import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// Emits a single self-contained dist/index.html — open directly, no server.
export default defineConfig({
  base: "./",
  plugins: [react(), viteSingleFile()],
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 4000,
    assetsInlineLimit: 100000000,
  },
});
