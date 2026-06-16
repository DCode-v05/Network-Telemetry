import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// Emits a single self-contained dist/index.html so the dashboard can be opened
// directly from disk (file://) with no server — matching the repo's original
// "self-contained report" property, but built from a real React app.
export default defineConfig({
  base: "./",
  plugins: [react(), viteSingleFile()],
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 4000,
    assetsInlineLimit: 100000000,
  },
});
